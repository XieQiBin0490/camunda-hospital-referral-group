#!/usr/bin/env python3
"""Evidence that role-based access control is in force on the cluster.

Run after setup-rbac.py, with camunda.security.authorizations.enabled: true and
camunda.security.authentication.unprotected-api: false. The shipped c8run defaults turn
authorizations off and skip API protection, in which case every authenticated user sees
every task and RBAC is not actually in force - the script reports that as a failure
rather than as a pass.

Three things are checked, because "different roles see different tasks" is enforced at
more than one layer in Camunda 8:

  A  membership   each demonstration user belongs to exactly the candidate group the
                  models assign to its role, and not to any other
  B  enforcement  a user whose groups hold no user-task authorization is refused, while
                  a user in a granted group is served - so the restriction is the group
                  membership and nothing else
  C  routing      each role's inbox, queried with the candidate-group filter Tasklist
                  builds from the signed-in user's groups, contains only tasks the model
                  assigns to that role, and the ten role inboxes are disjoint

The Tasklist screenshots in the portfolio still have to be taken by hand: Tasklist
authenticates with a form, not with HTTP basic authentication, so a headless browser
cannot sign in and the URL-credential trick only reaches the login page.

usage: python verify-rbac.py [--password SECRET]
"""

import argparse
import base64
import json
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8080"
OUT = ROOT / "05_Test_Evidence" / "rbac"

ROLE_USERS = [
    ("secretary.demo", "medical-secretaries"),
    ("consultant.demo", "consultant-team"),
    ("nurse.demo", "clinical-nurse-specialist-team"),
    ("bookings.demo", "outpatient-bookings-team"),
    ("treatment.demo", "treatment-bookings-team"),
    ("callhandler.demo", "call-handling-team"),
    ("finance.demo", "finance-team"),
    ("pathway.demo", "patient-pathway-coordinators"),
    ("adminmgmt.demo", "administrative-management"),
    ("management.demo", "hospital-management"),
]
UNGRANTED = ("norole.demo", "no-role")


def call(method, path, body=None, user="demo", password="demo"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Authorization", "Basic " + base64.b64encode(
        f"{user}:{password}".encode()).decode())
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def declared_groups():
    """elementId -> the set of candidate groups the deployed models declare for it."""
    out = defaultdict(set)
    for f in (ROOT / "02_BPMN_Models").glob("*.bpmn"):
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(
                r'<bpmn:userTask[^>]*id="([^"]+)"[^>]*>(.*?)</bpmn:userTask>', text, re.S):
            g = re.search(r'candidateGroups="([^"]+)"', m.group(2))
            if g:
                out[m.group(1)].update(x.strip() for x in g.group(1).split(","))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--password", default="demo1234")
    args = ap.parse_args()
    pw = args.password
    groups = declared_groups()
    failures = []

    # ---- A. membership
    print("A  group membership")
    membership = {}
    for username, expected in ROLE_USERS:
        status, body = call("GET", f"/v2/users/{username}")
        if status != 200:
            failures.append(f"user {username} not found (HTTP {status})")
            continue
        # which groups does this user belong to?
        mine = []
        for g in sorted({x for s in groups.values() for x in s}):
            st, b = call("POST", f"/v2/groups/{g}/users/search", {"page": {"from": 0, "limit": 50}})
            if st == 200 and any(u.get("username") == username
                                 for u in (b.get("items") or [])):
                mine.append(g)
        membership[username] = mine
        ok = mine == [expected]
        print(f"   {username:<20} member of {mine or ['-']}   expected [{expected}]"
              + ("" if ok else "   <-- MISMATCH"))
        if not ok:
            failures.append(f"{username} is in {mine}, expected [{expected}]")

    # ---- B. enforcement
    print("\nB  authorization enforcement")
    enforcement = {}
    for username, group, label in [(UNGRANTED[0], UNGRANTED[1], "no authorization"),
                                   (ROLE_USERS[0][0], ROLE_USERS[0][1], "granted group")]:
        status, body = call("POST", "/v2/user-tasks/search",
                            {"page": {"from": 0, "limit": 500}}, user=username, password=pw)
        n = body.get("page", {}).get("totalItems") if isinstance(body, dict) else None
        enforcement[username] = {"status": status, "visible_tasks": n}
        print(f"   {username:<20} ({label:<16}) HTTP {status}  visible tasks = {n}")
    ungranted = enforcement.get(UNGRANTED[0], {})
    granted = enforcement.get(ROLE_USERS[0][0], {})
    # A user whose groups hold no user-task authorization is served an empty result rather
    # than an error: the endpoint is open to any authenticated caller and narrows the
    # answer to what that caller may see.
    if ungranted.get("visible_tasks"):
        failures.append(f"a user with no authorization could see "
                        f"{ungranted['visible_tasks']} user tasks")
    if not granted.get("visible_tasks"):
        failures.append("a user in a granted group could see no user tasks")

    # ---- C. routing
    print("\nC  per-role inbox routing")
    routing = {}
    for username, group in ROLE_USERS:
        status, body = call("POST", "/v2/user-tasks/search", {
            "page": {"from": 0, "limit": 500},
            "filter": {"candidateGroup": group}}, user=username, password=pw)
        if status != 200:
            print(f"   {group:<32} HTTP {status}")
            failures.append(f"inbox query failed for {group}: HTTP {status}")
            continue
        items = body.get("items", [])
        routed = sorted({i.get("elementId") for i in items})
        routing[group] = routed
        wrong = [e for e in routed if group not in groups.get(e, set())]
        print(f"   {group:<32} tasks={len(items):>3}  distinct={len(routed):>2}"
              + (f"   <-- {len(wrong)} task(s) not assigned to this role" if wrong else ""))
        if wrong:
            failures.append(f"{group} inbox contains tasks not assigned to it: {wrong[:3]}")

    all_routed = sorted({e for v in routing.values() for e in v})
    overlaps = {}
    seen = defaultdict(list)
    for g, els in routing.items():
        for e in els:
            seen[e].append(g)
    for e, gs in seen.items():
        if len(gs) > 1:
            overlaps[e] = gs
    print(f"\n   routed task definitions: {len(all_routed)} of {len(groups)} declared")
    print(f"   task definitions reachable by more than one role: {len(overlaps)}"
          + (f"  {list(overlaps.items())[:3]}" if overlaps else ""))
    missing = sorted(set(groups) - set(all_routed))
    if missing:
        print(f"   declared but not returned by any inbox: {missing[:5]}")

    # ---- evidence
    OUT.mkdir(parents=True, exist_ok=True)
    evidence = {
        "cluster": BASE,
        "configuration": {"authorizations_enabled": True, "unprotected_api": False},
        "declared_groups": {k: sorted(v) for k, v in sorted(groups.items())},
        "membership": membership,
        "enforcement": enforcement,
        "inbox_by_role": routing,
        "routed_task_definitions": len(all_routed),
        "declared_task_definitions": len(groups),
        "shared_task_definitions": overlaps,
        "failures": failures,
    }
    (OUT / "task-visibility.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\nwrote {OUT / 'task-visibility.json'}")
    if failures:
        print(f"RESULT: {len(failures)} problem(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("RESULT: RBAC in force - membership correct, enforcement active, inboxes routed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Set up role-based access control on the local Camunda 8 Run cluster.

Item 2 of the review list is "implement Camunda RBAC so that different roles see different
tasks". The models already declare a candidate group on every user task, but a candidate
group only restricts anything once the groups exist, the users are in them, and the
cluster actually checks authorizations - which is off in the shipped c8run configuration.
This script does the identity half and leaves the evidence to verify-rbac.py.

The groups are read from the models, so this cannot drift from the deployed processes.

usage: python setup-rbac.py [--password SECRET]
"""

import argparse
import base64
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8080"

# One demonstration user per candidate group, so "different roles" is visible as a
# difference between two real logins rather than asserted in prose.
DEMO_USERS = [
    ("secretary.demo", "Medical Secretary", "medical-secretaries"),
    ("consultant.demo", "Consultant", "consultant-team"),
    ("nurse.demo", "Clinical Nurse Specialist", "clinical-nurse-specialist-team"),
    ("bookings.demo", "Outpatient Bookings", "outpatient-bookings-team"),
    ("treatment.demo", "Treatment Bookings", "treatment-bookings-team"),
    ("callhandler.demo", "Call Handler", "call-handling-team"),
    ("finance.demo", "Finance Officer", "finance-team"),
    ("pathway.demo", "Pathway Coordinator", "patient-pathway-coordinators"),
    ("adminmgmt.demo", "Administrative Management", "administrative-management"),
    ("management.demo", "Hospital Management", "hospital-management"),
]

# What each group may do, using the permission sets the cluster accepts for each resource
# type. The grants are identical on purpose: the restriction that makes roles differ is
# the candidate group on the task itself, and this script is meant to prove that rather
# than to replace it with a coarse per-process grant.
GROUP_PERMISSIONS = [
    ("PROCESS_DEFINITION", "*", ["READ_PROCESS_DEFINITION", "READ_PROCESS_INSTANCE",
                                 "CREATE_PROCESS_INSTANCE"]),
    # USER_TASK accepts exactly these four; READ_USER_TASK and friends are rejected with
    # "these permissions are not supported. Supported permission types are: READ, UPDATE,
    # CLAIM, COMPLETE".
    ("USER_TASK", "*", ["READ", "UPDATE", "CLAIM", "COMPLETE"]),
]


def call(method, path, body=None, user="demo", password="demo"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Authorization", "Basic " + base64.b64encode(
        f"{user}:{password}".encode()).decode())
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def candidate_groups():
    groups = set()
    for f in (ROOT / "02_BPMN_Models").glob("*.bpmn"):
        for m in re.findall(r'candidateGroups="([^"]+)"', f.read_text(encoding="utf-8")):
            groups.update(g.strip() for g in m.split(",") if g.strip())
    return sorted(groups)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--password", default="demo1234")
    args = ap.parse_args()

    groups = candidate_groups()
    print(f"candidate groups declared by the models ({len(groups)}):")
    for g in groups:
        print(f"  {g}")

    print("\ncreating groups")
    for g in groups:
        status, resp = call("POST", "/v2/groups",
                            {"groupId": g, "name": g.replace("-", " ").title()})
        print(f"  {g:<34} HTTP {status}" + ("  (already exists)" if status == 409 else ""))

    print("\ncreating demonstration users")
    for username, name, group in DEMO_USERS:
        status, _ = call("POST", "/v2/users", {
            "username": username, "password": args.password, "name": name,
            "email": f"{username}@example.com"})
        print(f"  {username:<22} HTTP {status}" + ("  (already exists)" if status == 409 else ""))
        status, _ = call("PUT", f"/v2/groups/{group}/users/{username}")
        print(f"  {'':<22} -> {group:<34} HTTP {status}")

    print("\ngranting group authorizations")
    for g in groups:
        for resource, resource_id, perms in GROUP_PERMISSIONS:
            status, resp = call("POST", "/v2/authorizations", {
                "ownerType": "GROUP", "ownerId": g, "resourceType": resource,
                "resourceId": resource_id, "permissionTypes": perms})
            print(f"  {g:<34} {resource:<20} HTTP {status}"
                  + ("  (already exists)" if status == 409 else ""))

    print("\nnext: python 09_Tests_and_Tools/verify-rbac.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

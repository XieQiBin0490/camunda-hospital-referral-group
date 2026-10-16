#!/usr/bin/env python3
"""Correct the form-binding attribute on every user task in the delivered models.

The models ask the engine to resolve each user task's form from the deployment the instance
belongs to. They express that with

    <zeebe:formDefinition formId="..." binding="deployment" />

but `binding` is not an attribute of zeebe:formDefinition. The element takes `formId`,
`formKey`, `externalReference`, `bindingType` and `versionTag`, and `bindingType` is an enum
of exactly `deployment`, `latest` and `versionTag` (checked against
zeebe-bpmn-model:8.9.0). An unknown attribute is not an error the engine rejects, so what
happened instead is worse than a failure:

  * Camunda Modeler flagged all 99 of them as `unknown attribute <binding>` - 29 warnings
    on O1 alone, which is exactly its formDefinition count;
  * the engine ignored the attribute and fell back to the default binding, which is
    `latest`, not `deployment`.

With `latest`, an instance renders whichever version of that form was deployed most
recently, whoever deployed it. That is how a teammate deploying their own copy of the forms
made every drop-down disappear: their older text-box forms became the latest versions. And
where a form was never deployed at all, the task fails to open instead.

This rewrites the attribute in place and is idempotent.

usage: python fix-form-binding.py [--check]
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "02_BPMN_Models"

# binding="X" -> bindingType="X", inside a zeebe:formDefinition element only.
PATTERN = re.compile(r'(<zeebe:formDefinition\b[^>]*?)\bbinding="([^"]+)"')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    total = 0
    for path in sorted(MODELS.glob("*.bpmn")):
        text = path.read_text(encoding="utf-8")
        fixed, n = PATTERN.subn(r'\1bindingType="\2"', text)
        already = text.count('bindingType="')
        print(f"  {path.name:<44} fixed={n:<3} already correct={already}")
        total += n
        if n and not args.check:
            path.write_text(fixed, encoding="utf-8")

    # Anything left with the bare attribute would be a miss worth seeing.
    remaining = 0
    for path in sorted(MODELS.glob("*.bpmn")):
        remaining += len(re.findall(r'<zeebe:formDefinition\b[^>]*\bbinding="', 
                                    path.read_text(encoding="utf-8")))
    print(f"\n{total} attribute(s) rewritten; {remaining} incorrect one(s) remaining"
          + ("  (check mode, nothing written)" if args.check else ""))
    if not args.check:
        print("\nnext: python 09_Tests_and_Tools/validate-models.py 02_BPMN_Models/*.bpmn")
        print("      node 09_Tests_and_Tools/deploy-all.mjs")
    return 1 if remaining else 0


if __name__ == "__main__":
    sys.exit(main())

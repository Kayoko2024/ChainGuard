"""Intentional policy baseline creation; normal checks never rewrite it."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ["spec/risk-rules.json", "spec/identifiers.json", "spec/eip712.json", "spec/schemas/protocol.schema.json",
           *[f"gateway/src/chainguard_gateway/{name}.py" for name in ("policy", "approvals", "canonical", "crypto")]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--review-draft-update", help="Explicit reason for revising this unaccepted stage's draft")
    args = parser.parse_args()
    manifest = {"version": 1, "policy_epoch": "1", "purpose": "Identical deterministic B/C policy and approval validation", 
                "files": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}}
    path = ROOT / "config/phase3-policy-freeze.json"
    if args.check:
        if json.loads(path.read_text()) != manifest:
            raise SystemExit("B/C policy baseline drift")
        print("Frozen B/C shared policy matches all 8 sources")
    else:
        if path.exists():
            if not args.review_draft_update:
                raise SystemExit("Policy already frozen; review a version change instead of silently overwriting")
            history = ROOT / "config/phase3-policy-draft-revisions.json"
            revisions = json.loads(history.read_text()) if history.exists() else []
            revisions.append({"reason": args.review_draft_update, "before": json.loads(path.read_text()), "after": manifest})
            history.write_text(json.dumps(revisions, indent=2) + "\n")
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        print("B/C shared policy baseline created; normal runs use --check")


if __name__ == "__main__":
    main()

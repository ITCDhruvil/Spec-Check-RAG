"""Bootstrap golden_set/manifest.json from validation_results."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django

django.setup()

from eval.golden_eval import bootstrap_manifest, DEFAULT_MANIFEST


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Phase 7 golden manifest")
    parser.add_argument(
        "--input",
        type=Path,
        default=BACKEND.parent / "sample-docs" / "validation_results",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_MANIFEST,
    )
    args = parser.parse_args()

    manifest = bootstrap_manifest(args.input.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    enabled = sum(1 for d in manifest["documents"] if d.get("enabled"))
    print(f"Wrote {args.out} ({enabled} enabled documents)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

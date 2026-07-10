"""
Index the two missing benchmark docs (744bea43, 6fde1046) so phase6 benchmark
can run against the full 8-doc golden set.

Usage:
    python eval/index_benchmark_docs.py
    python eval/index_benchmark_docs.py --doc-ids 744bea43 6fde1046
"""

import argparse
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from apps.documents.models import Document
from apps.intelligence.services.orchestrator import IntelligenceOrchestrator

DEFAULT_DOC_IDS = ["744bea43", "6fde1046"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--doc-ids",
        nargs="+",
        default=DEFAULT_DOC_IDS,
        help="Document ID prefixes to index",
    )
    args = parser.parse_args()

    for prefix in args.doc_ids:
        docs = Document.objects.filter(id__startswith=prefix)
        if not docs.exists():
            print(f"[SKIP] No doc matching {prefix}")
            continue
        doc = docs.first()
        print(f"[START] {prefix} -> {doc.id}")
        try:
            result = IntelligenceOrchestrator.run(str(doc.id), regenerate=True)
            print(
                f"[OK]    {prefix} chunks={result['chunk_count']} "
                f"insights={result['insight_count']}"
            )
        except Exception as exc:
            print(f"[FAIL]  {prefix} error={exc}")


if __name__ == "__main__":
    main()

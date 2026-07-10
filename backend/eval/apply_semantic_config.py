"""Apply SemanticConfiguration to the existing Azure Search index in place.

Semantic config is a metadata-only schema change — it does NOT require deleting
or re-embedding vectors. This pushes the updated schema (same fields + vector
search + new semantic_search) via create_or_update_index, preserving all documents.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django
django.setup()
sys.stdout.reconfigure(encoding="utf-8")

import apps.chat.services.azure_search_service as svc

# Force the builder to run (bypass the in-process early-return guard) and push
# the schema via create_or_update_index.
svc._index_ready = False
svc.ensure_search_index()

from django.conf import settings
from apps.chat.services.azure_search_service import _index_client

idx = _index_client().get_index(settings.AZURE_SEARCH_INDEX_NAME)
print("index:", idx.name)
print("fields:", len(idx.fields))
print("semantic_search:", idx.semantic_search)
if idx.semantic_search and idx.semantic_search.configurations:
    for c in idx.semantic_search.configurations:
        print("  config:", c.name)

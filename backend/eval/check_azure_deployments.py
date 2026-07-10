"""Quick Azure OpenAI deployment smoke test."""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django

django.setup()

from django.conf import settings

from apps.intelligence.services.model_routing import model_for_tier
from apps.intelligence.services.openai_service import OpenAIService


def try_deployment(name: str) -> None:
    client = OpenAIService()
    try:
        data, usage = client.chat_json(
            system="Respond with valid JSON only.",
            user='Return {"deployment_ok": true}',
            model=name,
        )
        print(f"  OK  {name} — tokens={usage.get('total_tokens')} response={data}")
    except Exception as exc:
        print(f"  FAIL {name} — {exc}")


def main() -> None:
    print("Azure OpenAI deployment check")
    print(f"  Endpoint: {settings.AZURE_OPENAI_ENDPOINT}")
    print(f"  AI_PROVIDER: {settings.AI_PROVIDER}")
    print(f"  STRONG (model_for_tier): {model_for_tier('strong')}")
    print(f"  FAST  (model_for_tier): {model_for_tier('fast')}")
    print()
    for dep in [
        settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
        settings.AZURE_OPENAI_CHAT_DEPLOYMENT_FAST,
        model_for_tier("strong"),
        model_for_tier("fast"),
    ]:
        if dep:
            try_deployment(dep)


if __name__ == "__main__":
    main()

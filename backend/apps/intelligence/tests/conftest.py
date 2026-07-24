import os

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings.ci" if os.environ.get("CI") else "config.settings.development",
)

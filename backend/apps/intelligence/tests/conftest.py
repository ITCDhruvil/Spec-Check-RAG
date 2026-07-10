import os

import django
import pytest

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings.ci" if os.environ.get("CI") else "config.settings.development",
)


def pytest_configure():
    django.setup()


@pytest.fixture(scope="session")
def django_db_setup():
    """Offline golden eval does not require database tables."""
    yield

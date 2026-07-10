"""
End-to-end project setup helper: create DB (if possible), migrate, seed admin.

Run from repo root via setup.ps1 / setup.bat, or manually:
  cd backend && venv\\Scripts\\python ..\\scripts\\setup_project.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"


def _load_env_file() -> None:
    env_path = BACKEND_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _parse_database_url(url: str) -> dict:
    normalized = url.replace("postgres://", "postgresql://", 1)
    parsed = urlparse(normalized)
    db_name = (parsed.path or "").lstrip("/")
    if not db_name:
        raise ValueError("DATABASE_URL is missing database name.")
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "user": unquote(parsed.username or "postgres"),
        "password": unquote(parsed.password or ""),
        "dbname": db_name,
    }


def ensure_database() -> bool:
    """Create PostgreSQL database if it does not exist. Returns True on success."""
    import psycopg
    from psycopg import sql

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL is not set in backend/.env")
        return False

    try:
        params = _parse_database_url(db_url)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return False

    target_db = params["dbname"]
    admin_db = os.environ.get("SETUP_POSTGRES_ADMIN_DB", "postgres")

    try:
        with psycopg.connect(
            host=params["host"],
            port=params["port"],
            user=params["user"],
            password=params["password"],
            dbname=admin_db,
            autocommit=True,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
                if cur.fetchone():
                    print(f"Database '{target_db}' already exists.")
                    return True
                cur.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_db))
                )
                print(f"Created database '{target_db}'.")
                return True
    except Exception as exc:
        print(f"WARNING: Could not auto-create database '{target_db}': {exc}")
        print(
            "Create it manually, e.g.:\n"
            f"  CREATE DATABASE {target_db};"
        )
        return False


def run_django_setup(admin_password: str | None) -> bool:
    os.chdir(BACKEND_DIR)
    sys.path.insert(0, str(BACKEND_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

    try:
        import django

        django.setup()
    except Exception as exc:
        print(f"ERROR: Django setup failed: {exc}")
        return False

    from django.core.management import call_command
    from django.db import connection

    try:
        connection.ensure_connection()
        print("Database connection OK.")
    except Exception as exc:
        print(f"ERROR: Cannot connect to database: {exc}")
        print("Check DATABASE_URL in backend/.env and ensure PostgreSQL is running.")
        return False

    print("Running migrations...")
    call_command("migrate", interactive=False, verbosity=1)

    print("Ensuring admin user...")
    if admin_password:
        if len(admin_password) < 10:
            print("ERROR: Admin password must be at least 10 characters.")
            return False
        call_command("ensure_admin_user", password=admin_password, reset_password=True)
    else:
        call_command("ensure_admin_user")

    # Ensure runtime directories exist
    for folder in ("media", "chroma_data"):
        path = BACKEND_DIR / folder
        path.mkdir(parents=True, exist_ok=True)
        print(f"Ready: {path.relative_to(REPO_ROOT)}")

    return True


def main() -> int:
    _load_env_file()

    admin_password = None
    for arg in sys.argv[1:]:
        if arg.startswith("--admin-password="):
            admin_password = arg.split("=", 1)[1]

    if not ensure_database():
        # Still try migrate — DB may already exist but CREATE failed due to permissions.
        pass

    if not run_django_setup(admin_password):
        return 1

    print("\nBackend setup complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

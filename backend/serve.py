"""Serve the backend with waitress (production-grade WSGI for Windows).

Usage: python serve.py [host] [port]
Defaults match manage.py (development settings) so behavior is identical to
`manage.py runserver`, just faster: multi-threaded, production-grade I/O.
Set DJANGO_SETTINGS_MODULE=config.settings.production to serve prod settings.
"""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000

    from django.core.wsgi import get_wsgi_application
    from waitress import serve

    application = get_wsgi_application()

    # Stale-job watchdog: anything left mid-processing by a previous server
    # run gets re-enqueued or failed, so no document shows "processing" forever.
    try:
        from django.core.management import call_command

        call_command("sweep_stale_jobs", max_age_minutes=30)
    except Exception as exc:  # never block startup on the sweep
        print(f"stale-job sweep failed: {exc}")

    print(f"Serving on http://{host}:{port} (waitress, threads=8)")
    serve(
        application,
        host=host,
        port=port,
        threads=8,
        # Buffer large request bodies (uploads) to temp files instead of RAM.
        max_request_body_size=200 * 1024 * 1024,
        # Long-running requests (LLM calls) must not be reaped.
        channel_timeout=600,
    )


if __name__ == "__main__":
    main()

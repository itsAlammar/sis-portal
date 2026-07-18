"""WSGI entry point for production servers.

    gunicorn --workers 2 --bind 0.0.0.0:8000 wsgi:app

SIS_SECRET_KEY must be set in the environment (all workers need the same
key or sessions will break).
"""

from webapp import app  # noqa: F401

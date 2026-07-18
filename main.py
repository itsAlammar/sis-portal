"""Entry point for the Student Information System CLI."""

from database import get_connection, initialize_database
from cli import run_cli


def main():
    conn = get_connection()
    initialize_database(conn)
    try:
        run_cli(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

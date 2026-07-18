"""Operational commands that shouldn't live in the web UI.

Usage:
    python manage.py create-user <username> <role> [--teacher-id N]
    python manage.py reset-password <username>
    python manage.py backup [--dir backups] [--keep 30]
    python manage.py list-users

Passwords are prompted for interactively (never passed on the command
line, where they would land in shell history).
"""

import argparse
import getpass
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from database import DB_PATH, get_connection, initialize_database
from auth_service import AuthService
from exceptions import SISError


def _prompt_password() -> str:
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Confirm password: "):
        sys.exit("Passwords do not match.")
    return password


def cmd_create_user(conn, args):
    auth = AuthService(conn)
    user = auth.create_user(args.username, _prompt_password(), args.role,
                            teacher_id=args.teacher_id)
    print(f"Created {user.role} account '{user.username}' (id {user.user_id}).")


def cmd_reset_password(conn, args):
    auth = AuthService(conn)
    user = auth.get_user_by_username(args.username)
    if user is None:
        sys.exit(f"No user named '{args.username}'.")
    auth.set_user_password(user.user_id, _prompt_password())
    print(f"Password updated for '{user.username}'.")


def cmd_list_users(conn, args):
    users = AuthService(conn).list_users()
    if not users:
        print("No staff accounts yet. Create one with: python manage.py create-user <name> admin")
        return
    for u in users:
        linked = f" teacher_id={u.teacher_id}" if u.teacher_id else ""
        print(f"{u.user_id:>4}  {u.username:<20} {u.role:<10} {u.status}{linked}")


def cmd_backup(conn, args):
    """Consistent online backup via SQLite's backup API -- safe to run
    while the web app is serving requests. Keeps the newest --keep files."""
    backup_dir = Path(args.dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_path = backup_dir / f"sis-{stamp}.db"
    target = sqlite3.connect(target_path)
    with target:
        conn.backup(target)
    target.close()
    print(f"Backup written to {target_path}")

    backups = sorted(backup_dir.glob("sis-*.db"))
    for old in backups[: max(0, len(backups) - args.keep)]:
        old.unlink()
        print(f"Pruned old backup {old}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-user", help="Create a staff account")
    p.add_argument("username")
    p.add_argument("role", choices=["admin", "registrar", "teacher"])
    p.add_argument("--teacher-id", type=int, default=None,
                   help="teachers.teacher_id to link (required for the teacher role)")
    p.set_defaults(func=cmd_create_user)

    p = sub.add_parser("reset-password", help="Reset a staff account's password")
    p.add_argument("username")
    p.set_defaults(func=cmd_reset_password)

    p = sub.add_parser("list-users", help="List staff accounts")
    p.set_defaults(func=cmd_list_users)

    p = sub.add_parser("backup", help=f"Back up {DB_PATH.name} (safe while the app runs)")
    p.add_argument("--dir", default=str(DB_PATH.parent / "backups"))
    p.add_argument("--keep", type=int, default=30, help="how many backups to retain")
    p.set_defaults(func=cmd_backup)

    args = parser.parse_args()
    conn = get_connection()
    initialize_database(conn)
    try:
        args.func(conn, args)
    except SISError as e:
        sys.exit(str(e))
    finally:
        conn.close()


if __name__ == "__main__":
    main()

"""Administrator CLI; uses the configured DB. No HTTP self-assignment."""
import argparse
from app.core.errors import DomainError
from app.db.session import SessionLocal
from app.services.assignments import assign_coach
from sqlalchemy.exc import SQLAlchemyError


def main():
    parser = argparse.ArgumentParser(description="Assign, transfer or revoke a Member's Coach.")
    parser.add_argument("--member-id", type=int, required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--coach-id", type=int)
    target.add_argument("--unassign", action="store_true")
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    try:
        with SessionLocal() as db:
            change = assign_coach(db, args.member_id, args.coach_id, args.actor, args.reason)
        print(f"Assignment event: {change}" if change else "Assignment unchanged.")
    except DomainError as exc:
        parser.exit(1, f"{exc.code}: {exc.detail}\n")
    except SQLAlchemyError:
        parser.exit(1, "Database tidak tersedia; periksa target konfigurasi dan migrasi.\n")


if __name__ == "__main__":
    main()

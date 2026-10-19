import argparse
import getpass
import json
from pathlib import Path
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.entities import User, Movement, ReferenceProfile
from app.core.security import passwords
from app.core.config import settings
from app.repositories.training import seed_movements


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coach-email")
    parser.add_argument("--coach-name", default="Pelatih SilatSense")
    args = parser.parse_args()
    with SessionLocal() as db:
        seed_movements(db)
        for path in sorted(Path(settings.reference_root).rglob("*.v1.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("provenance", {}).get("debug_partial"):
                continue
            if not db.scalar(
                select(ReferenceProfile).where(
                    ReferenceProfile.movement == data["movement"],
                    ReferenceProfile.variant == data["variant"],
                    ReferenceProfile.version == data["version"],
                )
            ):
                db.add(
                    ReferenceProfile(
                        movement=data["movement"],
                        variant=data["variant"],
                        version=data["version"],
                        artifact_path=path.relative_to(
                            settings.reference_root
                        ).as_posix(),
                        evaluator_type=data["evaluator_type"],
                    )
                )
        if args.coach_email:
            if db.scalar(select(User).where(User.email == args.coach_email.lower())):
                raise ValueError("Email already exists; no role changes performed.")
            password = getpass.getpass("New coach password (minimum 8 characters): ")
            if len(password) < 8 or len(password) > 128:
                raise ValueError("Password must be 8–128 characters")
            db.add(
                User(
                    name=args.coach_name,
                    email=args.coach_email.lower(),
                    password_hash=passwords.hash(password),
                    role="COACH",
                )
            )
        db.commit()
    print("Movements and measured reference profiles registered.")


if __name__ == "__main__":
    main()

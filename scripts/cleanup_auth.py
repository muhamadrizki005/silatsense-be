"""Delete expired recovery tokens/rate buckets; never print recipients or tokens."""

from sqlalchemy import delete
from app.db.session import SessionLocal
from app.models.entities import AuthRateBucket, RecoveryToken, now


def main():
    with SessionLocal() as db:
        for model in (AuthRateBucket, RecoveryToken):
            db.execute(delete(model).where(model.expires_at <= now()))
        db.commit()
    print("Expired auth metadata cleanup completed")


if __name__ == "__main__":
    main()

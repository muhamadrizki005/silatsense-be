from sqlalchemy import select

from app.models.entities import Movement

MOVEMENTS = (
    ("kuda_kuda", "Kuda-kuda"), ("pukulan", "Pukulan"),
    ("tangkisan", "Tangkisan"), ("tendangan", "Tendangan"),
)
PUBLIC_TO_INTERNAL = {"kuda-kuda": "kuda_kuda", **{slug: slug for slug, _ in MOVEMENTS if slug != "kuda_kuda"}}


def seed_movements(db):
    for order, (slug, name) in enumerate(MOVEMENTS, 1):
        row = db.scalar(select(Movement).where(Movement.slug == slug))
        if row is None:
            db.add(Movement(slug=slug, name=name, display_order=order))
        elif row.display_order == 0:
            row.display_order = order
    # Curated descriptions/guides are deliberately not fabricated or overwritten.


def active_movements(db):
    return db.scalars(select(Movement).where(
        Movement.active.is_(True), Movement.slug.in_([slug for slug, _ in MOVEMENTS]),
    ).order_by(Movement.display_order, Movement.id)).all()


def find_movement(db, slug):
    internal = PUBLIC_TO_INTERNAL.get(slug)
    if internal is None:
        return None
    return db.scalar(select(Movement).where(Movement.slug == internal, Movement.active.is_(True)))

from pydantic import ValidationError

from app.core.config import settings
from app.core.errors import DomainError
from app.repositories.evaluations import EvaluationRepository
from app.repositories.profiles import activity_summary
from app.repositories.training import active_movements, find_movement
from app.schemas.domain import Capability, GuideItem, TrainingCatalog, TrainingModule, TrainingPrep, UploadConfig


def module_data(db, row):
    profiles = EvaluationRepository(db).profiles(row.slug)
    return TrainingModule(
        slug="kuda-kuda" if row.slug == "kuda_kuda" else row.slug,
        name=row.name, order=row.display_order, description=row.description,
        level=row.level, estimatedDurationSeconds=row.estimated_duration_seconds,
        capability=Capability(
            scoringAvailable=bool(profiles), reason=None if profiles else "reference_not_ready",
            referenceVersions=sorted({profile["version"] for profile in profiles}),
        ),
    )


def catalog(db, user):
    return TrainingCatalog(
        modules=[module_data(db, row) for row in active_movements(db)],
        statistics=activity_summary(db, user.id),
    )


def required_movement(db, slug):
    row = find_movement(db, slug)
    if row is None:
        raise DomainError(404, "not_found", "Kategori gerakan tidak tersedia.")
    return row


def sourced_guides(items):
    guides = []
    for item in items if isinstance(items, list) else []:
        try:
            guide = GuideItem.model_validate(item)
            if guide.text.strip() and guide.source.strip():
                guides.append(guide)
        except ValidationError:
            continue
    return guides


def preparation(db, slug):
    row = required_movement(db, slug)
    return TrainingPrep(module=module_data(db, row),
                        checklist=sourced_guides(row.checklist), guides=sourced_guides(row.guides))


def upload_config(db, slug):
    row = required_movement(db, slug)
    return UploadConfig(
        movementSlug="kuda-kuda" if row.slug == "kuda_kuda" else row.slug,
        acceptedMimeTypes=["video/mp4", "video/quicktime", "video/webm"],
        maxBytes=settings.max_video_mb * 1024 * 1024, maxDurationSeconds=settings.max_video_seconds,
        recommendedDurationSeconds=row.estimated_duration_seconds,
    )

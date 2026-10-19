from collections import defaultdict
from math import isfinite

from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session

from app.models.entities import CoachProfile, EvaluationSession, MemberProfile, User, TrainingSession, MediaAsset
from app.schemas.domain import ActivitySummary, SimilarityGroup


def lock_user(db: Session, user_id: int) -> User | None:
    return db.scalar(select(User).where(User.id == user_id).with_for_update()
                     .execution_options(populate_existing=True))


def profile_row(db: Session, user: User):
    model = MemberProfile if user.role == "MEMBER" else CoachProfile
    return db.get(model, user.id)


def activity_summary(db: Session, user_id: int) -> ActivitySummary:
    def owns(column):
        return column == user_id if isinstance(user_id, int) else column.in_(user_id)
    rows_statement = select(EvaluationSession.movement, EvaluationSession.score, EvaluationSession.result_json,
        EvaluationSession.analyzer_version, EvaluationSession.reference_version).outerjoin(
        TrainingSession, TrainingSession.id == EvaluationSession.training_session_id,
    ).where(owns(EvaluationSession.user_id), or_(
        EvaluationSession.training_session_id.is_(None),
        (TrainingSession.processing_status == "completed") & TrainingSession.deleted_at.is_(None),
    )).execution_options(yield_per=500)
    durations = db.scalars(select(MediaAsset.duration_seconds).join(
        TrainingSession, TrainingSession.id == MediaAsset.session_id,
    ).where(owns(TrainingSession.user_id), TrainingSession.processing_status == "completed",
            TrainingSession.deleted_at.is_(None)).execution_options(yield_per=500))
    duration_count = 0
    duration_total = 0.0
    for duration in durations:
        if isfinite(duration) and duration >= 0:
            duration_count += 1
            duration_total += duration
    completed_count = db.scalar(select(func.count()).select_from(TrainingSession).where(
        owns(TrainingSession.user_id), TrainingSession.processing_status == "completed",
        TrainingSession.deleted_at.is_(None)))
    # Preserve summaries for unlinked legacy results until their backfill exists.
    completed_count += db.scalar(select(func.count()).select_from(EvaluationSession).where(
        owns(EvaluationSession.user_id), EvaluationSession.training_session_id.is_(None)))
    groups = defaultdict(lambda: [0.0, 0])
    scored = 0
    eligible = 0
    for row in db.execute(rows_statement):
        if row.score is not None:
            scored += 1
        result = row.result_json if isinstance(row.result_json, dict) else {}
        model = result.get("model", {})
        analysis = result.get("analysis", {})
        if not isinstance(model, dict) or not isinstance(analysis, dict):
            continue
        versions = (analysis.get("method"), row.analyzer_version,
                    model.get("feature_version"), row.reference_version)
        if (row.movement not in {"kuda_kuda", "pukulan", "tangkisan", "tendangan"}
                or row.score is None or not isfinite(row.score) or not 0 <= row.score <= 100
                or not all(isinstance(value, str) and value for value in versions)):
            continue
        group = groups[(row.movement, *versions)]
        group[0] += row.score
        group[1] += 1
        eligible += 1
    summaries = [SimilarityGroup(
        movementSlug="kuda-kuda" if key[0] == "kuda_kuda" else key[0],
        method=key[1], analyzerVersion=key[2], featureVersion=key[3], referenceVersion=key[4],
        averageScore=round(values[0] / values[1], 2), sampleCount=values[1],
    ) for key, values in sorted(groups.items())]
    return ActivitySummary(
        completedSessionCount=completed_count, totalDurationSeconds=duration_total, durationSampleCount=duration_count,
        scoredSessionCount=scored, excludedScoreCount=completed_count - eligible,
        similarityGroups=summaries,
    )

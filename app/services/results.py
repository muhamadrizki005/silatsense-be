from sqlalchemy import select

from app.core.errors import DomainError
from app.intelligence.features.presentation import metadata
from app.models.entities import AnalysisJob, EvaluationSession, MediaAsset, TrainingSession, now
from app.schemas.results import AcknowledgedOut, EvaluationOut, PoseOut
from app.services.sessions import _authorized_lock, get_session, identifier


def completed_evaluation(db, owner_id, value):
    session = get_session(db, owner_id, value)
    require_completed(session)
    row = db.scalar(select(EvaluationSession).where(EvaluationSession.training_session_id == session.id))
    if row is None:
        raise DomainError(409, "evaluation_pending", "Hasil evaluasi belum tersedia.")
    return session, row


def require_completed(session):
    if session.processing_status == "failed":
        raise DomainError(409, "analysis_failed", "Analisis sesi gagal.")
    if session.processing_status != "completed":
        raise DomainError(409, "evaluation_pending", "Analisis sesi belum selesai.")


def read_evaluation(db, owner_id, value):
    session, row = completed_evaluation(db, owner_id, value)
    return evaluation_out(session, row)


def evaluation_out(session, row):
    data = row.result_json
    analysis, model = data["analysis"], data["model"]
    index, seconds = analysis.get("key_frame"), analysis.get("key_frame_time")
    keyframe = dict(index=index, timeSeconds=seconds) if index is not None and seconds is not None else None
    temporal = analysis.get("method") == "coach-reference-dtw"
    reasons = ["repetition_count_not_supported"]
    if not temporal:
        reasons.append("temporal_analysis_not_supported")
    else:
        reasons.append("correctness_not_validated")
        if not (data.get("coach_comparison") or {}).get("semanticPhasesAvailable"):
            reasons.append("semantic_phases_not_annotated")
    if keyframe is None:
        reasons.append("keyframe_unavailable")
    if analysis.get("features_compared") is None:
        reasons.append("features_compared_unavailable")
    if "measurements" not in data:
        reasons.append("measurements_not_stored")
    if not data.get("pose") and not (data.get("pose_timeline") or {}).get("frames"):
        reasons.append("pose_not_stored" if "pose" not in data else "pose_unavailable")
    if model.get("feature_version") is None:
        reasons.append("feature_version_not_stored")
    issues = []
    for issue in data["issues"]:
        _, unit = metadata(issue["feature"])
        issues.append(dict(feature=issue["feature"], bodyPart=issue["body_part"],
                           deviation=issue["deviation"], unit=unit,
                           severity=issue["severity"], feedback=issue["feedback"]))
    return EvaluationOut(
        id=str(row.id), sessionId=str(session.id),
        movementSlug="kuda-kuda" if row.movement == "kuda_kuda" else row.movement,
        evaluatedAt=row.created_at, analysisStatus=row.status, score=row.score,
        scoreReason=None if row.score is not None else "correctness_not_validated" if row.status == "reference_compared" else row.status,
        method=analysis.get("method", "static-reference-pose"),
        matchedVariant=row.matched_variant, analyzerVersion=row.analyzer_version,
        featureVersion=model.get("feature_version"), referenceVersion=row.reference_version,
        poseStatus=data["pose_status"], framesProcessed=analysis["frames_processed"],
        validPoseFrames=analysis["valid_pose_frames"], featuresCompared=analysis.get("features_compared"),
        keyFrame=keyframe, measurements=data.get("measurements", []), issues=issues,
        unavailableReasons=reasons,
        coachComparison=data.get("coach_comparison"),
    )


def read_pose(db, owner_id, value):
    session, row = completed_evaluation(db, owner_id, value)
    pose = row.result_json.get("pose")
    timeline = row.result_json.get("pose_timeline")
    return PoseOut(sessionId=str(session.id), pose=pose,
                   timeline=timeline,
                   reason=None if pose or timeline and timeline.get("frames") else "pose_not_stored" if "pose" not in row.result_json else "pose_unavailable")


def acknowledge(db, user, value):
    owner, version = user.id, user.auth_version
    _authorized_lock(db, owner, version)
    session = db.scalar(select(TrainingSession).where(
        TrainingSession.id == identifier(value), TrainingSession.user_id == owner,
        TrainingSession.deleted_at.is_(None),
    ).with_for_update())
    if session is None:
        raise DomainError(404, "not_found", "Sesi tidak ditemukan.")
    require_completed(session)
    session.acknowledged_at = session.acknowledged_at or now()
    response = AcknowledgedOut(acknowledgedAt=session.acknowledged_at)
    db.commit()
    return response


def delete_session(db, user, value):
    owner, version = user.id, user.auth_version
    _authorized_lock(db, owner, version)
    sid = identifier(value)
    # Consistent with worker/cleanup lock order. Do not lock another owner's job.
    owned = db.scalar(select(TrainingSession.id).where(TrainingSession.id == sid, TrainingSession.user_id == owner))
    if owned is None:
        raise DomainError(404, "not_found", "Sesi tidak ditemukan.")
    job = db.scalar(select(AnalysisJob).where(AnalysisJob.session_id == sid).with_for_update())
    session = db.scalar(select(TrainingSession).where(TrainingSession.id == sid).with_for_update())
    media = db.scalar(select(MediaAsset).where(MediaAsset.session_id == sid).with_for_update())
    timestamp = now()
    session.deleted_at = session.deleted_at or timestamp
    if media:
        media.deletion_requested_at = media.deletion_requested_at or timestamp
    if job and job.state in {"queued", "processing"}:
        job.state, job.claim_token, job.last_error_code, job.finished_at = "failed", None, "media_deleted", timestamp
        # Keep the reader lease: cleanup waits for inference to close its file.
        session.processing_status, session.error_code, session.completed_at = "failed", "media_deleted", timestamp
    db.commit()

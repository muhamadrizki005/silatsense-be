import hashlib
from sqlalchemy import select

from app.core.errors import DomainError
from app.models.entities import CoachProfile, EvaluationSession, FeedbackDraft, FollowUpTask, IdempotencyRecord, ReviewHead, ReviewRevision, RetryIntent, TrainingSession, now
from app.repositories.assignments import identity, require_member
from app.repositories.profiles import lock_user
from app.repositories.reviews import task_out
from app.schemas.reviews import DraftOut, PublishedReview, RetryOut
from app.services.sessions import canonical_hash, get_session, identifier, _authorized_lock


def coach_gate(db, actor, value):
    actor_id, version = actor.id, actor.auth_version
    sid = identifier(value)
    owner = db.scalar(select(TrainingSession.user_id).where(TrainingSession.id == sid))
    db.rollback()
    if owner is None:
        raise DomainError(404, "not_found", "Sesi tidak ditemukan.")
    _, assignment = require_member(db, actor_id, owner, lock=True)
    user = lock_user(db, actor_id)
    if not user or user.role != "COACH" or user.auth_version != version:
        raise DomainError(401, "unauthenticated", "Silakan masuk kembali.")
    session = db.scalar(select(TrainingSession).where(TrainingSession.id == sid).with_for_update())
    if session.deleted_at:
        raise DomainError(404, "not_found", "Sesi tidak ditemukan.")
    return user, assignment, session


def draft_row(db, session_id, assignment):
    return db.scalar(select(FeedbackDraft).where(FeedbackDraft.session_id == session_id,
        FeedbackDraft.assignment_event_id == assignment.event_id, FeedbackDraft.author_id == assignment.coach_id))


def draft_out(db, row, user):
    return DraftOut(version=row.version, author=identity(user, db.get(CoachProfile, user.id)),
        updatedAt=row.updated_at, **row.payload)


def save_draft(db, actor, value, data):
    user, assignment, session = coach_gate(db, actor, value)
    row = draft_row(db, session.id, assignment)
    if data.expectedVersion != (row.version if row else 0):
        raise DomainError(409, "version_conflict", "Versi draft sudah berubah.")
    if row is None:
        row = FeedbackDraft(session_id=session.id, author_id=user.id, assignment_event_id=assignment.event_id, version=0)
        db.add(row)
    row.version += 1
    row.payload, row.updated_at = data.model_dump(exclude={"expectedVersion"}), now()
    result = draft_out(db, row, user)
    db.commit()
    return result


def idempotency(db, user_id, operation, key, data):
    if not 1 <= len(key) <= 128 or not key.strip():
        raise DomainError(422, "validation_error", "Idempotency-Key wajib 1–128 karakter.")
    digest, fingerprint = hashlib.sha256(key.encode()).hexdigest(), canonical_hash(data.model_dump())
    record = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.user_id == user_id,
        IdempotencyRecord.operation == operation, IdempotencyRecord.key_hash == digest))
    if record and record.fingerprint != fingerprint:
        raise DomainError(409, "idempotency_conflict", "Key sudah dipakai untuk payload berbeda.")
    return record, digest, fingerprint


def publish(db, actor, value, data, key):
    user, assignment, session = coach_gate(db, actor, value)
    operation = f"review:{session.id}"
    record, digest, fingerprint = idempotency(db, user.id, operation, key, data)
    if record:
        return PublishedReview.model_validate(record.response_json)
    if session.processing_status != "completed" or not db.scalar(select(EvaluationSession.id).where(
            EvaluationSession.training_session_id == session.id).with_for_update()):
        raise DomainError(409, "analysis_failed" if session.processing_status == "failed" else "evaluation_pending",
                          "Evaluasi harus completed sebelum review diterbitkan.")
    head = db.get(ReviewHead, session.id)
    previous = db.get(ReviewRevision, head.review_id) if head else None
    draft = draft_row(db, session.id, assignment)
    if (data.expectedRevision != (previous.revision if previous else 0) or not draft
            or data.expectedDraftVersion != draft.version):
        raise DomainError(409, "version_conflict", "Versi review/draft sudah berubah.")
    if draft.payload["decision"] is None:
        raise DomainError(422, "decision_required", "Keputusan Coach wajib sebelum publish.")
    timestamp = now()
    row = ReviewRevision(session_id=session.id, author_id=user.id, assignment_event_id=assignment.event_id,
        revision=data.expectedRevision + 1, decision=draft.payload["decision"], payload={}, created_at=timestamp)
    # Allocate review/task IDs and finalize the snapshot in one transaction.
    # No incomplete snapshot is published; committed revisions are never edited.
    from sqlalchemy import insert
    values = dict(session_id=row.session_id, author_id=row.author_id, assignment_event_id=row.assignment_event_id,
        revision=row.revision, decision=row.decision, payload={}, created_at=timestamp)
    review_id = db.execute(insert(ReviewRevision).values(**values)).inserted_primary_key[0]
    task_ids = []
    for task in draft.payload["tasks"]:
        task_row = FollowUpTask(session_id=session.id, review_id=review_id, author_id=user.id,
            instruction=task["instruction"], status="open", created_at=timestamp, updated_at=timestamp)
        db.add(task_row)
        db.flush()
        task_ids.append(str(task_row.id))
    result = PublishedReview(id=str(review_id), revision=row.revision,
        author=identity(user, db.get(CoachProfile, user.id)), publishedAt=timestamp, decision=row.decision,
        note=draft.payload["note"], bodyAssessments=draft.payload["bodyAssessments"], taskIds=task_ids,
        supersedesReviewId=str(previous.id) if previous else None)
    from sqlalchemy import update
    db.execute(update(ReviewRevision).where(ReviewRevision.id == review_id).values(payload=result.model_dump(mode="json")))
    if head:
        head.review_id = review_id
    else:
        db.add(ReviewHead(session_id=session.id, review_id=review_id))
    db.delete(draft)
    db.add(IdempotencyRecord(user_id=user.id, operation=operation, key_hash=digest, fingerprint=fingerprint,
        session_id=session.id, response_json=result.model_dump(mode="json")))
    db.commit()
    return result


def retry_intent(db, user, value, data, key):
    uid, version = user.id, user.auth_version
    _authorized_lock(db, uid, version)
    session = get_session(db, uid, value)
    if session.processing_status not in {"completed", "failed"}:
        raise DomainError(409, "session_not_terminal", "Sesi belum terminal.")
    operation = f"retry:{session.id}"
    record, digest, fingerprint = idempotency(db, uid, operation, key, data)
    if record:
        return RetryOut.model_validate(record.response_json)
    row = RetryIntent(user_id=uid, source_session_id=session.id, created_at=now())
    db.add(row)
    db.flush()
    result = RetryOut(id=str(row.id), sourceSessionId=str(session.id), createdAt=row.created_at)
    db.add(IdempotencyRecord(user_id=uid, operation=operation, key_hash=digest, fingerprint=fingerprint,
        session_id=session.id, response_json=result.model_dump(mode="json")))
    db.commit()
    return result


def patch_task(db, user, value, data):
    uid, version = user.id, user.auth_version
    _authorized_lock(db, uid, version)
    row = db.scalar(select(FollowUpTask).join(TrainingSession, TrainingSession.id == FollowUpTask.session_id)
        .where(FollowUpTask.id == identifier(value), TrainingSession.user_id == uid,
               TrainingSession.deleted_at.is_(None)).with_for_update())
    if row is None:
        raise DomainError(404, "not_found", "Tugas tidak ditemukan.")
    if row.status != data.status:
        row.status, row.updated_at = data.status, now()
    result = task_out(row, db.get(ReviewRevision, row.review_id))
    db.commit()
    return result

"""What happens when a worker's answer arrives (or is produced locally)."""
import json
import shutil
from pathlib import Path
from typing import Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from .config import settings
from .models import KeyTable, Study

DISCLAIMER = "Research use only, not for clinical diagnosis"
FINAL_STATUSES = ("done", "failed")


class WorkerResult(BaseModel):
    """The agreed wrapper. Extra fields (volumes, detection...) are accepted and stored."""
    model_config = ConfigDict(extra="allow")

    key: str                              # the random key the backend sent with the job
    task: str                             # brain_mri | liver_ct
    status: Literal["success", "error"]
    result: Optional[dict] = None
    error: Optional[dict] = None          # {"code": ..., "message": ...}
    model: Optional[dict] = None          # {"name": ..., "version": ...}
    disclaimer: Optional[str] = None


def _find_study(db: Session, key: str) -> Study:
    row = db.query(KeyTable).filter_by(random_key=key).first()
    if not row:
        raise HTTPException(404, "Unknown job key")
    return db.get(Study, row.study_id)


def mark_processing(db: Session, key: str) -> None:
    study = _find_study(db, key)
    if study.status in ("anonymized", "queued"):
        study.status = "processing"
        db.commit()


def apply_result(db: Session, payload) -> Study:
    """Save a worker's answer and set the study status (done or failed)."""
    if isinstance(payload, dict):
        payload = WorkerResult(**payload)
    study = _find_study(db, payload.key)
    if study.status in FINAL_STATUSES:
        raise HTTPException(409, "This job already has a result")
    if payload.task != study.task:
        raise HTTPException(422, "The task of the result does not match the study")

    stored = payload.model_dump(exclude={"key"})  # the random key is not shown to the frontend
    if payload.status == "success":
        if payload.result is None:
            raise HTTPException(422, "A successful answer must contain 'result'")
        study.status = "done"
    else:
        error = payload.error or {}
        study.status = "failed"
        study.error_code = str(error.get("code", "MODEL_ERROR"))[:64]
        study.error_message = str(error.get("message", "The analysis failed."))[:500]
    study.result_json = json.dumps(stored)
    db.commit()

    # The anonymized copy is no longer needed in the hand-over area.
    shutil.rmtree(Path(settings.transfer_dir) / payload.key / "input", ignore_errors=True)
    return study


def result_view(study: Study) -> dict:
    """The one shape the frontend polls: the same keys whatever the status."""
    stored = json.loads(study.result_json) if study.result_json else {}
    error = None
    if study.status == "failed":
        error = {"code": study.error_code, "message": study.error_message}
    return {
        "study_id": study.id,
        "task": study.task,
        "status": study.status,
        "result": stored.get("result"),
        "model": stored.get("model"),
        "dummy": bool(stored.get("dummy", False)),
        "error": error,
        "disclaimer": stored.get("disclaimer") or DISCLAIMER,
    }

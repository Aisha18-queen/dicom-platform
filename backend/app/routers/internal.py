"""Endpoints used by the WORKERS, not by the frontend (hidden from /docs).

They are protected by a shared secret in the X-Worker-Secret header. In the
cloud they will also be reachable only from the compute zone (firewall rule).
"""
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .. import audit, results
from ..config import settings
from ..database import get_db


def require_worker(x_worker_secret: str = Header(default="")):
    if not secrets.compare_digest(x_worker_secret.encode(), settings.worker_secret.encode()):
        raise HTTPException(403, "Invalid worker secret")


router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    include_in_schema=False,
    dependencies=[Depends(require_worker)],
)


@router.post("/results")
def receive_result(payload: results.WorkerResult, db: Session = Depends(get_db)):
    study = results.apply_result(db, payload)
    audit.log(db, 0, "result", study.id)  # user 0 = the system; ids only
    return {"study_id": study.id, "status": study.status}


@router.post("/jobs/{key}/processing")
def job_started(key: str, db: Session = Depends(get_db)):
    results.mark_processing(db, key)
    return {"ok": True}

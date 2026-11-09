"""Hand a study to a worker. The mode is chosen with the QUEUE_MODE setting."""
import logging
import shutil
import time
from functools import lru_cache
from pathlib import Path

from fastapi import BackgroundTasks

from . import results
from .config import settings
from .database import SessionLocal
from .dummy_workers import dummy_brain_mri, dummy_liver_ct

log = logging.getLogger(__name__)


def _stage_input(anon_dir: Path, key: str) -> Path:
    """Copy the anonymized study into the hand-over area, in a folder named by
    the random key (never by study id). The worker only ever sees this folder."""
    dest = Path(settings.transfer_dir) / key / "input"
    shutil.copytree(anon_dir, dest, dirs_exist_ok=True)
    return dest


@lru_cache(maxsize=1)
def _celery():
    from celery import Celery  # imported here so the backend works without Celery in local/off mode
    return Celery("backend", broker=settings.celery_broker_url)


def dispatch(task: str, key: str, anon_dir: Path, background_tasks: BackgroundTasks) -> str:
    """Start the analysis. Returns the study's new status."""
    mode = settings.queue_mode
    if mode == "off":
        return "anonymized"
    input_dir = _stage_input(anon_dir, key)
    if mode == "local":
        background_tasks.add_task(run_local_job, task, key, input_dir)
        return "queued"
    if mode == "celery":
        # One queue per task (named brain_mri / liver_ct): each model has its own worker image.
        _celery().send_task("worker.run_job", args=[key, task], queue=task, retry=False)
        return "queued"
    raise ValueError(f"Unknown QUEUE_MODE: {mode}")


def run_local_job(task: str, key: str, input_dir: Path) -> None:
    """The DUMMY worker, running inside the backend (QUEUE_MODE=local)."""
    try:
        with SessionLocal() as db:
            results.mark_processing(db, key)
        time.sleep(settings.dummy_delay_seconds)
        if task == "brain_mri":
            payload = dummy_brain_mri(input_dir, key)
        else:
            output_dir = Path(settings.transfer_dir) / key / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            payload = dummy_liver_ct(input_dir, output_dir, key)
    except Exception:
        log.exception("Dummy worker failed")
        payload = {"key": key, "task": task, "status": "error",
                   "error": {"code": "MODEL_ERROR", "message": "The dummy worker failed."}}
    try:
        with SessionLocal() as db:
            results.apply_result(db, payload)
    except Exception:
        log.exception("Could not save the dummy result")

"""The worker task. It runs in the COMPUTE zone: it only sees the anonymized folder
and the random key, and it reports back to the backend over HTTP.

Start one worker per model, each listening to its own queue:
    celery -A worker.celery_app worker -Q brain_mri
    celery -A worker.celery_app worker -Q liver_ct
"""
import os
from pathlib import Path

import httpx

from .celery_app import app

# TODO (ML teammate): replace the dummy functions with the real ones:
#   run_brain_mri(input_dir, key) -> dict
#   run_liver_ct(input_dir, output_dir, key) -> dict
from .dummy_models import dummy_brain_mri as run_brain_mri
from .dummy_models import dummy_liver_ct as run_liver_ct

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")
WORKER_SECRET = os.environ.get("WORKER_SECRET", "dev-worker-secret")
TRANSFER_DIR = Path(os.environ.get("TRANSFER_DIR", "/data/transfer"))


def _post(path: str, body=None) -> None:
    response = httpx.post(f"{BACKEND_URL}{path}", json=body,
                          headers={"X-Worker-Secret": WORKER_SECRET}, timeout=30)
    response.raise_for_status()


@app.task(name="worker.run_job")
def run_job(key: str, task: str) -> None:
    input_dir = TRANSFER_DIR / key / "input"
    output_dir = TRANSFER_DIR / key / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    _post(f"/internal/jobs/{key}/processing")
    try:
        if task == "brain_mri":
            payload = run_brain_mri(input_dir, key)
        elif task == "liver_ct":
            payload = run_liver_ct(input_dir, output_dir, key)
        else:
            raise ValueError(f"Unknown task: {task}")
    except Exception:
        payload = {"key": key, "task": task, "status": "error",
                   "error": {"code": "MODEL_ERROR", "message": "The model failed to run."}}
    _post("/internal/results", payload)

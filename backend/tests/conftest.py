"""Runs before any test module: every test run gets a fresh database and fresh folders,
and the dummy worker runs locally without delay (no Redis needed)."""
import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.mkdtemp(), 'test.db').as_posix()}"
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp()
os.environ["TRANSFER_DIR"] = tempfile.mkdtemp()
os.environ["QUEUE_MODE"] = "local"
os.environ["DUMMY_DELAY_SECONDS"] = "0"
os.environ["WORKER_SECRET"] = "test-secret"

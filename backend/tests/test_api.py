from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import KeyTable
from tests.fake_dicom import FAKE
from tests.helpers import login, real_dicom_files

TASK = {"task": "liver_ct"}


def study_folders():
    return list(Path(settings.upload_dir).iterdir())


def test_health_and_login():
    with TestClient(app) as c:
        assert c.get("/health").json() == {"status": "ok"}
        assert c.post("/auth/login", data={"username": "admin", "password": "bad"}).status_code == 401
        h = login(c)
        assert c.get("/auth/me", headers=h).json()["role"] == "admin"


def test_upload_rejects_wrong_files():
    with TestClient(app) as c:
        h = login(c)
        bad = c.post("/studies", headers=h, data=TASK, files=[("files", ("a.txt", b"hello"))])
        assert bad.status_code == 400
        fake = c.post("/studies", headers=h, data=TASK, files=[("files", ("b.dcm", b"not dicom"))])
        assert fake.status_code == 400


def test_upload_anonymizes_and_stores_key():
    with TestClient(app) as c:
        h = login(c)
        r = c.post("/studies", headers=h, data=TASK, files=real_dicom_files(2))
        assert r.status_code == 201
        body = r.json()
        assert body["file_count"] == 2 and body["task"] == "liver_ct"
        assert body["status"] == "queued"          # QUEUE_MODE=local in the tests

        study_dir = Path(settings.upload_dir) / body["study_id"]
        assert not (study_dir / "raw").exists()                      # originals deleted
        assert len(list((study_dir / "anonymized").iterdir())) == 2  # anonymized copies kept

        # No file left on disk contains the fake patient's identity.
        for path in study_dir.rglob("*"):
            if path.is_file():
                data = path.read_bytes()
                assert FAKE["name"].encode() not in data
                assert FAKE["patient_id"].encode() not in data

        # The link key <-> patient exists in the key table (clinical zone only).
        with SessionLocal() as db:
            row = db.get(KeyTable, body["study_id"])
            assert row.patient_id == FAKE["patient_id"]
            assert len(row.random_key) == 32


def test_upload_rejects_task_that_does_not_match_the_files():
    with TestClient(app) as c:
        h = login(c)
        before = len(study_folders())
        r = c.post("/studies", headers=h, data={"task": "brain_mri"}, files=real_dicom_files(2))
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "MODALITY_MISMATCH"   # CT files, MRI task
        assert len(study_folders()) == before                      # nothing was kept


def test_detect_suggests_liver_ct_and_keeps_nothing():
    with TestClient(app) as c:
        h = login(c)
        r = c.post("/studies/detect", headers=h, files=real_dicom_files(1))
        assert r.status_code == 200
        body = r.json()
        assert body["suggested_task"] == "liver_ct"
        assert body["modality"] == "CT" and body["body_part"] == "ABDOMEN"
        assert not [p for p in study_folders() if p.name.startswith("_detect_")]


def test_task_list_for_the_selector():
    with TestClient(app) as c:
        h = login(c)
        tasks = c.get("/studies/tasks", headers=h).json()
        assert {t["id"] for t in tasks} == {"brain_mri", "liver_ct"}


def test_doctor_cannot_create_users():
    with TestClient(app) as c:
        h = login(c)
        c.post("/auth/users", headers=h, json={"username": "doc1", "password": "pw", "role": "doctor"})
        hd = login(c, "doc1", "pw")
        r = c.post("/auth/users", headers=hd, json={"username": "x", "password": "y"})
        assert r.status_code == 403

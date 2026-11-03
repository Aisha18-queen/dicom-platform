import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp()

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import KeyTable  # noqa: E402
from tests.fake_dicom import FAKE, make_fake_study  # noqa: E402


def login(client, user="admin", pwd="admin"):
    r = client.post("/auth/login", data={"username": user, "password": pwd})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def real_dicom_files(n=2):
    """n fake DICOM slices (fake patient DOE^JOHN), ready to upload."""
    folder = Path(tempfile.mkdtemp())
    make_fake_study(folder, slices=n)
    return [("files", (p.name, p.read_bytes())) for p in sorted(folder.iterdir())]


def test_health_and_login():
    with TestClient(app) as c:
        assert c.get("/health").json() == {"status": "ok"}
        assert c.post("/auth/login", data={"username": "admin", "password": "bad"}).status_code == 401
        h = login(c)
        assert c.get("/auth/me", headers=h).json()["role"] == "admin"


def test_upload_rejects_wrong_files():
    with TestClient(app) as c:
        h = login(c)
        bad = c.post("/studies", headers=h, files=[("files", ("a.txt", b"hello"))])
        assert bad.status_code == 400
        fake = c.post("/studies", headers=h, files=[("files", ("b.dcm", b"not dicom"))])
        assert fake.status_code == 400


def test_upload_anonymizes_and_stores_key():
    with TestClient(app) as c:
        h = login(c)
        r = c.post("/studies", headers=h, files=real_dicom_files(2))
        assert r.status_code == 201
        body = r.json()
        assert body["file_count"] == 2 and body["status"] == "anonymized"

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


def test_doctor_cannot_create_users():
    with TestClient(app) as c:
        h = login(c)
        c.post("/auth/users", headers=h, json={"username": "doc1", "password": "pw", "role": "doctor"})
        hd = login(c, "doc1", "pw")
        r = c.post("/auth/users", headers=hd, json={"username": "x", "password": "y"})
        assert r.status_code == 403

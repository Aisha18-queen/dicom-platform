import tempfile
from pathlib import Path

from app.database import SessionLocal
from app.models import KeyTable
from tests.fake_dicom import make_fake_study


def login(client, user="admin", pwd="admin"):
    r = client.post("/auth/login", data={"username": user, "password": pwd})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def real_dicom_files(n=2):
    """n fake DICOM slices (fake patient DOE^JOHN, CT abdomen), ready to upload."""
    folder = Path(tempfile.mkdtemp())
    make_fake_study(folder, slices=n)
    return [("files", (p.name, p.read_bytes())) for p in sorted(folder.iterdir())]


def key_of(study_id):
    """The random key of a study (what a worker would be given)."""
    with SessionLocal() as db:
        return db.get(KeyTable, study_id).random_key

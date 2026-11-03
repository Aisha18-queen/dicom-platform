import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import audit
from ..anonymizer import anonymize_folder
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, require_role
from ..models import KeyTable, Study, User
from ..upload_validation import check_all_dicom, extract_zip, save_upload

router = APIRouter(prefix="/studies", tags=["studies"])


@router.post("", status_code=201)
async def upload_study(
    files: list[UploadFile],
    db: Session = Depends(get_db),
    user: User = Depends(require_role("doctor", "admin")),
):
    if not files:
        raise HTTPException(400, "No files received")
    if len(files) > settings.max_files:
        raise HTTPException(413, f"Too many files (max {settings.max_files})")

    study_id = str(uuid.uuid4())
    study_dir = Path(settings.upload_dir) / study_id
    raw_dir = study_dir / "raw"
    anon_dir = study_dir / "anonymized"
    raw_dir.mkdir(parents=True)
    try:
        # 1. Receive and validate (type, size, count, DICOM signature)
        n = 0
        for f in files:
            name = (f.filename or "").lower()
            if name.endswith(".zip"):
                tmp = study_dir / "tmp.zip"
                await save_upload(f, tmp)
                n += extract_zip(tmp, raw_dir, n)
                tmp.unlink()
            elif name.endswith(".dcm"):
                n += 1
                await save_upload(f, raw_dir / f"{n:06d}.dcm")
            else:
                raise HTTPException(400, "Only .dcm files or a .zip are accepted")
        check_all_dicom(raw_dir)

        # 2. Anonymize. Originals are deleted as soon as this succeeds.
        try:
            result = anonymize_folder(raw_dir, anon_dir, delete_originals=True)
        except Exception:
            # Don't include the error text: it could contain patient data.
            raise HTTPException(422, "The study could not be anonymized (is it a valid DICOM study?)")
    except Exception:
        shutil.rmtree(study_dir, ignore_errors=True)  # never keep a half-processed upload
        raise

    # 3. Save the study and the pseudonymization link (key <-> patient)
    db.add(Study(id=study_id, owner_id=user.id, file_count=result.file_count, status="anonymized"))
    db.flush()  # make sure the study row exists before the key table row refers to it
    db.add(KeyTable(
        study_id=study_id,
        random_key=result.study_key,
        patient_id=result.patient_id,
        patient_name=result.patient_name,
    ))
    db.commit()
    audit.log(db, user.id, "upload", study_id)  # ids only, never patient data
    # NEXT STEP: send anonymized files + random key to the compute zone (Celery)
    return {
        "study_id": study_id,
        "file_count": result.file_count,
        "status": "anonymized",
        "warnings": result.warnings,
    }


@router.get("")
def list_studies(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Study)
    if user.role != "admin":
        q = q.filter_by(owner_id=user.id)
    return [{"id": s.id, "status": s.status, "file_count": s.file_count} for s in q.all()]


@router.get("/{study_id}")
def get_study(study_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = db.get(Study, study_id)
    if not s or (user.role != "admin" and s.owner_id != user.id):
        raise HTTPException(404, "Study not found")
    audit.log(db, user.id, "view", study_id)
    return {"id": s.id, "status": s.status, "file_count": s.file_count}

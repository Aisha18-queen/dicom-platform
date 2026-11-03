import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="doctor")  # doctor | admin


class Study(Base):
    __tablename__ = "studies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), default="uploaded")
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # TODO later: task (brain_mri | liver_ct), random_key, result fields


class KeyTable(Base):
    """Pseudonymization key table: random key <-> real patient.

    This is the ONLY place where a patient identity is stored. It lives in the
    clinical zone's database and must never be sent to the compute zone.
    TODO (security dossier): encryption at rest for these two columns.
    """
    __tablename__ = "key_table"
    study_id: Mapped[str] = mapped_column(ForeignKey("studies.id"), primary_key=True)
    random_key: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    patient_id: Mapped[str] = mapped_column(String(128), default="")
    patient_name: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditLog(Base):
    """Audit trail. Must NEVER contain PHI: only ids and action names."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(32))  # login | upload | view | export
    object_id: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

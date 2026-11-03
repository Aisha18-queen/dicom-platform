from sqlalchemy.orm import Session

from .models import AuditLog


def log(db: Session, user_id: int, action: str, object_id: str = ""):
    """Record an event. Pass only ids, never patient data."""
    db.add(AuditLog(user_id=user_id, action=action, object_id=object_id))
    db.commit()

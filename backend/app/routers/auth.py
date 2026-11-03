from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import audit
from ..database import get_db
from ..deps import get_current_user, require_role
from ..models import User
from ..security import create_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class NewUser(BaseModel):
    username: str
    password: str
    role: str = "doctor"


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password")
    audit.log(db, user.id, "login")
    return {"access_token": create_token(user.id, user.role), "token_type": "bearer"}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "role": user.role}

@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_role("admin"))):
    users = db.query(User).all()
    return [{"id": u.id, "username": u.username, "role": u.role} for u in users]

@router.post("/users", status_code=201)
def create_user(body: NewUser, db: Session = Depends(get_db), _: User = Depends(require_role("admin"))):
    if body.role not in ("doctor", "admin"):
        raise HTTPException(400, "Role must be doctor or admin")
    if db.query(User).filter_by(username=body.username).first():
        raise HTTPException(409, "Username already exists")
    db.add(User(username=body.username, hashed_password=hash_password(body.password), role=body.role))
    db.commit()
    return {"username": body.username, "role": body.role}

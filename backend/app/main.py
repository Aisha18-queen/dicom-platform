from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from . import models
from .config import settings
from .database import Base, SessionLocal, engine
from .routers import auth, internal, studies
from .security import hash_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)  # simple for now; use Alembic later
    with SessionLocal() as db:
        if not db.query(models.User).filter_by(username=settings.admin_username).first():
            db.add(models.User(
                username=settings.admin_username,
                hashed_password=hash_password(settings.admin_password),
                role="admin",
            ))
            db.commit()
    yield


app = FastAPI(title="DICOM Anonymization & AI Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(studies.router)
app.include_router(internal.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health")
def health():
    return {"status": "ok"}

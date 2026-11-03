# DICOM Anonymization & AI Platform

## Run locally
1. Install Docker Desktop.
2. `cp .env.example .env` and edit the passwords.
3. `docker compose up --build`
4. Open http://localhost:8000/docs (interactive API docs).
   Log in with the admin user from `.env` using the "Authorize" button.

## Run tests (without Docker)
    cd backend
    python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    pytest

## What exists
- Login (JWT), roles (doctor/admin), admin-only user creation
- Upload (.dcm files or .zip) with type/size/count validation
- Audit log (ids and actions only, no PHI)

## Next to build
1. `backend/app/anonymizer/` + tag-dump test
2. Task selector + metadata check (`routing.py`)
3. Celery job + worker, results endpoint
4. Frontend

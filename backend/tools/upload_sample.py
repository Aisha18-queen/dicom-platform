"""Demo of the whole flow against the running server.

Start the server with the dummy worker switched on:
    PowerShell:  $env:QUEUE_MODE="local"; uvicorn app.main:app --reload
Then, in a second terminal (from the backend folder):
    python tools/upload_sample.py
"""
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
zip_path = Path("sample_data/fake_ct_study.zip")
files = [("files", (zip_path.name, zip_path.read_bytes(), "application/zip"))]

login = httpx.post(f"{BASE}/auth/login", data={"username": "admin", "password": "admin"})
headers = {"Authorization": f"Bearer {login.json()['access_token']}"}


def show(label, r):
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
    print(label, r.status_code, body)
    return body


# 1. Ask the backend which task fits these files (pre-fills the selector)
detected = show("1. detect:", httpx.post(f"{BASE}/studies/detect", headers=headers, files=files, timeout=60))
task = detected.get("suggested_task") or "liver_ct"

# 2. Upload with a WRONG task: must be rejected, nothing stored
show("2. wrong task (brain_mri):",
     httpx.post(f"{BASE}/studies", headers=headers, files=files, data={"task": "brain_mri"}, timeout=60))

# 3. Upload with the right task: anonymized, then queued
uploaded = show(f"3. right task ({task}):",
                httpx.post(f"{BASE}/studies", headers=headers, files=files, data={"task": task}, timeout=60))
study_id = uploaded["study_id"]

# 4. Follow the job, like the frontend will (poll the status every second)
status = uploaded["status"]
for _ in range(30):
    if status in ("done", "failed", "anonymized"):
        break
    time.sleep(1)
    status = httpx.get(f"{BASE}/studies/{study_id}", headers=headers).json()["status"]
    print("   status:", status)

# 5. Read the result
if status == "anonymized":
    print("The queue is off. Restart the server with QUEUE_MODE=local to see the job run.")
else:
    show("5. result:", httpx.get(f"{BASE}/studies/{study_id}/result", headers=headers))

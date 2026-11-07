"""Demo of the whole upload flow against the running server.

Run from the backend folder (server running in another terminal):
    python tools/upload_sample.py
"""
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
zip_path = Path("sample_data/fake_ct_study.zip")
files = [("files", (zip_path.name, zip_path.read_bytes(), "application/zip"))]

login = httpx.post(f"{BASE}/auth/login", data={"username": "admin", "password": "admin"})
headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

# 1. Ask the backend which task fits these files (pre-fills the selector)
r = httpx.post(f"{BASE}/studies/detect", headers=headers, files=files, timeout=60)
print("1. detect:", r.status_code, r.json())
task = r.json().get("suggested_task") or "liver_ct"

# 2. Upload with a WRONG task: must be rejected, nothing stored
r = httpx.post(f"{BASE}/studies", headers=headers, files=files, data={"task": "brain_mri"}, timeout=60)
print("2. wrong task (brain_mri):", r.status_code, r.json())

# 3. Upload with the right task: accepted and anonymized
r = httpx.post(f"{BASE}/studies", headers=headers, files=files, data={"task": task}, timeout=60)
print(f"3. right task ({task}):", r.status_code, r.json())

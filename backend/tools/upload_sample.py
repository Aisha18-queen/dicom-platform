import httpx
from pathlib import Path

BASE = "http://127.0.0.1:8000"

login = httpx.post(f"{BASE}/auth/login", data={"username": "admin", "password": "admin"})
token = login.json()["access_token"]

zip_path = Path("sample_data/fake_ct_study.zip")
with open(zip_path, "rb") as f:
    r = httpx.post(
        f"{BASE}/studies",
        headers={"Authorization": f"Bearer {token}"},
        files=[("files", (zip_path.name, f, "application/zip"))],
        timeout=60,
    )
print(r.status_code, r.json())
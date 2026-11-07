import sqlite3
from pathlib import Path

import pydicom

# Newest study folder
studies = sorted(Path("data/uploads").iterdir(), key=lambda p: p.stat().st_mtime)
study = studies[-1]
print("Study folder:", study.name)
print("Contents:", [p.name for p in study.iterdir()], "<- there must be NO 'raw' folder")

files = sorted((study / "anonymized").glob("*.dcm"))
print("Anonymized files:", len(files))

# Tags of the first file
ds = pydicom.dcmread(files[0])
print("PatientName:", ds.PatientName, "<- must be a random key")
print("PatientID:", ds.PatientID)
print("PatientBirthDate:", repr(ds.PatientBirthDate), "<- must be empty")
print("Has InstitutionName:", "InstitutionName" in ds, "<- must be False")
print("Modality:", ds.Modality, "| Body part:", ds.BodyPartExamined, "<- must be kept")

# Search the raw bytes for the fake patient's original data
fakes = [b"DOE^JOHN", b"PID-98765432", b"General Hospital", b"SMITH^ALICE"]
leaked = any(f in p.read_bytes() for p in files for f in fakes)
print("Original identifiers found in files:", leaked, "<- must be False")

# The key table (the only place where the real identity is kept)
try:
    con = sqlite3.connect("dev.db")
    for row in con.execute("select random_key, patient_id, patient_name from key_table"):
        print("Key table row:", row)
except Exception as e:
    print("Could not read key table:", e)
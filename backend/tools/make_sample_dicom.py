"""Creates a ZIP of fake DICOM slices to test the upload endpoint in /docs.

Run from the backend folder:
    python -m tools.make_sample_dicom
Output: sample_data/fake_ct_study.zip  (fake patient "DOE^JOHN", no real data)
"""
import shutil
from pathlib import Path

from tests.fake_dicom import make_fake_study

out = Path("sample_data")
folder = out / "fake_ct_study"
shutil.rmtree(folder, ignore_errors=True)
make_fake_study(folder, slices=5)
zip_path = shutil.make_archive(str(out / "fake_ct_study"), "zip", folder)
print(f"Created {zip_path}")

"""Upload validation: file type, size and count (goal 5.1)."""
import os
import zipfile
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .config import settings

CHUNK = 1024 * 1024


def is_dicom(path: Path) -> bool:
    """Standard DICOM files have 'DICM' at byte offset 128."""
    with open(path, "rb") as f:
        f.seek(128)
        return f.read(4) == b"DICM"


async def save_upload(upload: UploadFile, dest: Path) -> int:
    """Stream to disk, aborting if the file is too big. Returns size in bytes."""
    limit = settings.max_file_mb * CHUNK
    size = 0
    with open(dest, "wb") as out:
        while chunk := await upload.read(CHUNK):
            size += len(chunk)
            if size > limit:
                raise HTTPException(413, f"File too large (max {settings.max_file_mb} MB)")
            out.write(chunk)
    return size


def extract_zip(zip_path: Path, dest_dir: Path, start_index: int) -> int:
    """Safely extract a ZIP: flat filenames (no zip-slip), size and count limits."""
    if not zipfile.is_zipfile(zip_path):
        raise HTTPException(400, "Not a valid ZIP file")
    total, count = 0, 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            total += info.file_size
            count += 1
            if total > settings.max_total_mb * CHUNK or count > settings.max_files:
                raise HTTPException(413, "ZIP too large or contains too many files")
            target = dest_dir / f"{start_index + count:06d}.dcm"  # ignore original names
            with zf.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())
    return count


def check_all_dicom(folder: Path):
    files = [p for p in folder.iterdir() if p.is_file()]
    if not files:
        raise HTTPException(400, "No files received")
    if len(files) > settings.max_files:
        raise HTTPException(413, f"Too many files (max {settings.max_files})")
    bad = [p.name for p in files if not is_dicom(p)]
    if bad:
        raise HTTPException(400, f"{len(bad)} file(s) are not valid DICOM")
    return len(files)

"""Task routing: which model should process this study, and does the DICOM
metadata agree with the doctor's choice?

This runs on the RAW upload, BEFORE anonymization, because the anonymizer
removes some tags. Only Modality and BodyPartExamined are used for the
decision. Neither is patient information, so they can safely appear in
responses and logs. Patient identifiers are only counted, never returned.
"""
import re
from dataclasses import dataclass
from pathlib import Path

import pydicom
from fastapi import HTTPException
from pydicom.multival import MultiValue

# One entry per deployed model. Body parts are written in normalized form
# (upper case, letters only), so "Abdomen/Pelvis" becomes "ABDOMENPELVIS".
TASKS = {
    "brain_mri": {
        "label": "Brain MRI",
        "modality": "MR",
        "body_parts": {"BRAIN", "HEAD", "SKULL", "HEADNECK", "BRAINSTEM"},
    },
    "liver_ct": {
        "label": "Liver CT",
        "modality": "CT",
        "body_parts": {"LIVER", "ABDOMEN", "ABDOMENPELVIS", "ABDPELVIS", "ABDOMENPELV"},
    },
}


@dataclass
class StudyInfo:
    file_count: int
    modalities: set
    body_parts: set       # values as written in the files
    series_count: int
    study_count: int
    patient_count: int    # only a count: identifiers are never returned
    sequence: str = ""    # MRI sequence name, informational only


def _norm(value: str) -> str:
    return re.sub(r"[^A-Z]", "", value.upper())


def _error(code: str, message: str) -> HTTPException:
    return HTTPException(400, detail={"code": code, "message": message})


def _sequence_of(ds) -> str:
    name = str(ds.get("SequenceName", "") or "")
    if name:
        return name
    scanning = ds.get("ScanningSequence")
    if isinstance(scanning, (list, MultiValue)):
        return "/".join(str(s) for s in scanning)
    return str(scanning or "")


def read_study_info(folder: Path) -> StudyInfo:
    """Read the routing-relevant tags of every file (pixel data is skipped)."""
    modalities, body_parts, series, studies, patients = set(), set(), set(), set(), set()
    sequence = ""
    files = sorted(p for p in Path(folder).iterdir() if p.is_file())
    for path in files:
        try:
            ds = pydicom.dcmread(path, stop_before_pixels=True)
        except Exception:
            raise _error("INVALID_DICOM", "A file could not be read as DICOM.")
        modalities.add(str(ds.get("Modality", "")).upper())
        body_part = str(ds.get("BodyPartExamined", "")).strip()
        if body_part:
            body_parts.add(body_part)
        series.add(str(ds.get("SeriesInstanceUID", "")))
        studies.add(str(ds.get("StudyInstanceUID", "")))
        patients.add(str(ds.get("PatientID", "")))
        sequence = sequence or _sequence_of(ds)
    modalities.discard("")
    return StudyInfo(
        file_count=len(files), modalities=modalities, body_parts=body_parts,
        series_count=len(series), study_count=len(studies),
        patient_count=len(patients), sequence=sequence,
    )


def detect_task(info: StudyInfo):
    """Suggest a task from the metadata. Returns (task or None, confidence)."""
    parts = {_norm(p) for p in info.body_parts}
    candidates = []
    for task, spec in TASKS.items():
        if info.modalities != {spec["modality"]}:
            continue
        if not parts or parts & spec["body_parts"]:
            candidates.append(task)
    if len(candidates) == 1:
        return candidates[0], ("high" if parts else "low")
    return None, ""


def check_task(task: str, info: StudyInfo) -> list:
    """Raise an HTTP 400 if the files do not fit the chosen task.

    Returns a list of warnings for softer problems (for example a missing
    BodyPartExamined tag, which is common in real files).
    """
    if task not in TASKS:
        raise _error("UNKNOWN_TASK", f"Unknown task. Choose one of: {', '.join(TASKS)}.")
    spec = TASKS[task]

    # The anonymizer treats an upload as ONE patient, ONE study, ONE series.
    if info.patient_count > 1:
        raise _error("MULTIPLE_PATIENTS", "The upload contains files from more than one patient.")
    if info.study_count > 1:
        raise _error("MULTIPLE_STUDIES", "The upload contains more than one study.")
    if info.series_count > 1:
        raise _error("MULTIPLE_SERIES",
                     f"The upload contains {info.series_count} series. Upload one series at a time.")

    if info.modalities != {spec["modality"]}:
        found = ", ".join(sorted(info.modalities)) or "unknown"
        raise _error("MODALITY_MISMATCH",
                     f"{spec['label']} expects {spec['modality']} images, but the files are {found}.")

    warnings = []
    parts = {_norm(p) for p in info.body_parts}
    other_parts = set().union(*(s["body_parts"] for t, s in TASKS.items() if t != task))
    if not parts:
        warnings.append("BodyPartExamined is missing, so the body region could not be confirmed.")
    else:
        if {p for p in parts if p in other_parts and p not in spec["body_parts"]}:
            raise _error("BODY_PART_MISMATCH",
                         f"{spec['label']} was selected, but the body part in the files "
                         f"({', '.join(sorted(info.body_parts))}) points to a different task.")
        if {p for p in parts if p not in spec["body_parts"]}:
            warnings.append(f"Body part ({', '.join(sorted(info.body_parts))}) is not a usual "
                            f"region for {spec['label']}.")
    return warnings

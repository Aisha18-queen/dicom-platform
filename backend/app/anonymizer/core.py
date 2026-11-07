"""DICOM anonymization, based on the DICOM PS3.15 Basic Confidentiality Profile.

IMPORTANT: this is a *simplified* implementation. It covers the main rules of
the profile (remove/blank identifying tags, regenerate UIDs consistently,
delete private tags) plus generic safety rules (every Person Name and every
date/time is cleared). Before any use beyond the project, compare the tag lists
below with PS3.15 Table E.1-1 and document the differences in your security
dossier.

How a file is cleaned (see _clean_dataset):
  1. Private tags (odd group numbers)        -> deleted
  2. Tags in REMOVE_TAGS                     -> deleted
  3. Any element with VR "PN" (person name)  -> emptied
  4. Dates/times (VR DA/DT/TM) and BLANK_TAGS-> emptied
  5. UIDs (VR "UI")                          -> replaced by new random UIDs,
                                                the SAME old UID always gets the
                                                SAME new UID across the study
  6. Sequences (SQ)                          -> cleaned recursively
Then PatientName and PatientID are set to a random key.
"""
import shutil  # noqa: I001
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pydicom
from pydicom.datadict import tag_for_keyword
from pydicom.dataset import Dataset
from pydicom.multival import MultiValue
from pydicom.uid import generate_uid


class AnonymizationError(Exception):
    pass


def _tags(*keywords: str) -> set:
    """Turn DICOM keywords into tag numbers. Fails loudly on a typo."""
    result = set()
    for keyword in keywords:
        tag = tag_for_keyword(keyword)
        if tag is None:
            raise ValueError(f"Unknown DICOM keyword: {keyword}")
        result.add(tag)
    return result


# Tags that are deleted completely.
REMOVE_TAGS = _tags(
    "InstitutionName", "InstitutionAddress", "InstitutionalDepartmentName",
    "StationName", "ReferringPhysicianAddress", "ReferringPhysicianTelephoneNumbers",
    "PhysiciansOfRecord", "PerformingPhysicianName", "NameOfPhysiciansReadingStudy",
    "OperatorsName", "PatientBirthTime", "OtherPatientIDs", "OtherPatientNames",
    "PatientAge", "PatientSize", "PatientWeight", "PatientAddress",
    "PatientTelephoneNumbers", "PatientMotherBirthName", "MilitaryRank",
    "EthnicGroup", "Occupation", "AdditionalPatientHistory", "PatientComments",
    "ImageComments", "StudyDescription", "SeriesDescription", "DeviceSerialNumber",
    "RequestedProcedureDescription", "PerformedProcedureStepDescription",
    "AdmissionID", "IssuerOfPatientID",
)

# Tags that are kept but emptied.
BLANK_TAGS = _tags("PatientSex", "AccessionNumber", "StudyID")

# UIDs that describe *types* (not individual objects) must NOT be replaced,
# otherwise the file would no longer be a valid DICOM image.
KEEP_UIDS = _tags(
    "SOPClassUID", "ReferencedSOPClassUID", "TransferSyntaxUID",
    "ImplementationClassUID", "MediaStorageSOPClassUID",
)

DEIDENTIFICATION_METHOD = "PS3.15 Basic Profile (simplified)"


@dataclass
class AnonymizationResult:
    study_key: str            # random key: goes to the compute zone with the study
    patient_id: str           # ORIGINAL identity: goes ONLY in the clinical key table
    patient_name: str         # ORIGINAL identity: goes ONLY in the clinical key table
    file_count: int
    output_dir: Path
    warnings: list = field(default_factory=list)


def _new_uid(old: str, uid_map: dict) -> str:
    """Same old UID -> same new UID (keeps the study consistent)."""
    old = str(old)
    if old not in uid_map:
        uid_map[old] = generate_uid()
    return uid_map[old]


def _remap_uids(value, uid_map: dict):
    if isinstance(value, (list, MultiValue)):
        return [_new_uid(v, uid_map) for v in value]
    return _new_uid(value, uid_map)


def _clean_dataset(ds: Dataset, uid_map: dict) -> None:
    # list(ds) makes a copy, so we can delete elements while looping.
    for elem in list(ds):
        tag = elem.tag
        if tag.is_private or tag in REMOVE_TAGS:
            del ds[tag]
        elif elem.VR == "SQ":
            for item in elem.value:
                _clean_dataset(item, uid_map)
        elif elem.VR == "PN" or elem.VR in ("DA", "DT", "TM") or tag in BLANK_TAGS:
            elem.value = ""
        elif elem.VR == "UI" and tag not in KEEP_UIDS:
            elem.value = _remap_uids(elem.value, uid_map)


def anonymize_file(src: Path, dst: Path, study_key: str, uid_map: dict) -> list:
    """Anonymize one DICOM file. Returns a list of warnings."""
    warnings = []
    ds = pydicom.dcmread(src)

    # Text drawn into the pixels cannot be removed by editing tags.
    if str(ds.get("BurnedInAnnotation", "")).upper() == "YES":
        warnings.append("Image may contain burned-in text (BurnedInAnnotation=YES)")

    _clean_dataset(ds, uid_map)

    ds.PatientName = study_key
    ds.PatientID = study_key
    ds.PatientIdentityRemoved = "YES"
    ds.DeidentificationMethod = DEIDENTIFICATION_METHOD

    # The file header repeats the instance UID: keep it in sync.
    if "SOPInstanceUID" in ds and hasattr(ds, "file_meta"):
        ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID

    ds.save_as(dst, enforce_file_format=True)
    return warnings


def find_leaks(folder: Path, originals: list) -> list:
    """Safety net: search the raw bytes of every output file for original values.

    Returns a list of messages (never the values themselves, to avoid putting
    PHI in logs). Values shorter than 4 characters are ignored to avoid false alarms.
    """
    needles = [o.encode("utf-8") for o in originals if o and len(o) >= 4]
    leaks = []
    for path in sorted(Path(folder).iterdir()):
        data = path.read_bytes()
        for needle in needles:
            if needle in data:
                leaks.append(f"{path.name}: an original identifier is still present")
    return leaks


def anonymize_folder(src_dir: Path, dst_dir: Path, delete_originals: bool = False) -> AnonymizationResult:
    """Anonymize every file of one study.

    Output files get neutral names (000001.dcm, ...) because original file
    names can contain patient information.
    """
    src_dir, dst_dir = Path(src_dir), Path(dst_dir)
    files = sorted(p for p in src_dir.iterdir() if p.is_file())
    if not files:
        raise AnonymizationError("No files to anonymize")

    # Read the real identity once, BEFORE cleaning, for the clinical key table.
    first = pydicom.dcmread(files[0], stop_before_pixels=True)
    patient_id = str(first.get("PatientID", ""))
    patient_name = str(first.get("PatientName", ""))

    study_key = uuid.uuid4().hex
    uid_map: dict = {}
    warnings: list = []
    dst_dir.mkdir(parents=True, exist_ok=True)

    try:
        for i, path in enumerate(files, start=1):
            warnings += anonymize_file(path, dst_dir / f"{i:06d}.dcm", study_key, uid_map)
        leaks = find_leaks(dst_dir, [patient_id, patient_name])
        if leaks:
            raise AnonymizationError("; ".join(leaks))
    except Exception:
        shutil.rmtree(dst_dir, ignore_errors=True)  # never keep a half-anonymized study
        raise

    if delete_originals:
        shutil.rmtree(src_dir, ignore_errors=True)

    return AnonymizationResult(
        study_key=study_key,
        patient_id=patient_id,
        patient_name=patient_name,
        file_count=len(files),
        output_dir=dst_dir,
        warnings=sorted(set(warnings)),
    )

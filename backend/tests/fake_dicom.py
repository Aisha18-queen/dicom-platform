"""Builds fake DICOM studies with FAKE patient data, for tests and demos.

Nothing here is real patient data.
"""
from pathlib import Path

from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2"

# Fake identifiers we inject. The tests check that NONE of them survives.
FAKE = {
    "name": "DOE^JOHN",
    "patient_id": "PID-98765432",
    "birth_date": "19800101",
    "institution": "General Hospital Lyon",
    "physician": "SMITH^ALICE",
    "accession": "ACC-555123",
    "study_date": "20240315",
    "description": "CT abdomen for DOE",
    "private": "PRIVATE-SECRET-42",
    "nested": "NESTED^DOCTOR",
}


def make_fake_dicom(path: Path, study_uid: str, series_uid: str, number: int) -> None:
    sop_uid = generate_uid()
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = CT_IMAGE_STORAGE
    meta.MediaStorageSOPInstanceUID = sop_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128,
                     is_implicit_VR=False, is_little_endian=True)
    ds.SOPClassUID = CT_IMAGE_STORAGE
    ds.SOPInstanceUID = sop_uid
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.FrameOfReferenceUID = "1.2.826.0.1.3680043.8.498.1111"

    ds.PatientName = FAKE["name"]
    ds.PatientID = FAKE["patient_id"]
    ds.PatientBirthDate = FAKE["birth_date"]
    ds.PatientSex = "M"
    ds.InstitutionName = FAKE["institution"]
    ds.ReferringPhysicianName = FAKE["physician"]
    ds.AccessionNumber = FAKE["accession"]
    ds.StudyDate = FAKE["study_date"]
    ds.StudyDescription = FAKE["description"]

    ds.Modality = "CT"
    ds.BodyPartExamined = "ABDOMEN"
    ds.InstanceNumber = number

    # A private tag, and a person name hidden inside a sequence.
    ds.add_new(0x00090010, "LO", "ACME PRIVATE")
    ds.add_new(0x00091001, "LO", FAKE["private"])
    item = Dataset()
    item.RequestingPhysician = FAKE["nested"]
    ds.RequestAttributesSequence = Sequence([item])

    ds.Rows = 2
    ds.Columns = 2
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = b"\x00\x01" * 4

    ds.save_as(path, enforce_file_format=True)


def make_fake_study(folder: Path, slices: int = 3):
    """Create `slices` files in `folder`. Returns (study_uid, series_uid)."""
    folder.mkdir(parents=True, exist_ok=True)
    study_uid, series_uid = generate_uid(), generate_uid()
    for n in range(1, slices + 1):
        make_fake_dicom(folder / f"IM{n:04d}_DOE_JOHN.dcm", study_uid, series_uid, n)
    return study_uid, series_uid

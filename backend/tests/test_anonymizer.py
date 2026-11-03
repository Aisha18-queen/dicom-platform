"""Automated tag-dump test (proposal goal 5.1): proves no original identifier remains."""
import pydicom
import pytest

from app.anonymizer import anonymize_folder, find_leaks
from tests.fake_dicom import FAKE, make_fake_study

ORIGINALS = [
    FAKE["name"], FAKE["patient_id"], FAKE["birth_date"], FAKE["institution"],
    FAKE["physician"], FAKE["accession"], FAKE["study_date"], FAKE["description"],
    FAKE["private"], FAKE["nested"],
]


def dump_values(ds):
    """The 'tag dump': every value of every tag, including nested sequences."""
    for elem in ds:
        if elem.VR == "SQ":
            for item in elem.value:
                yield from dump_values(item)
        else:
            yield str(elem.value)
    if hasattr(ds, "file_meta"):
        yield from dump_values(ds.file_meta)


def all_tags(ds):
    for elem in ds:
        yield elem
        if elem.VR == "SQ":
            for item in elem.value:
                yield from all_tags(item)


@pytest.fixture
def study(tmp_path):
    src, dst = tmp_path / "raw", tmp_path / "anon"
    study_uid, series_uid = make_fake_study(src, slices=3)
    result = anonymize_folder(src, dst)
    return {"src": src, "dst": dst, "result": result,
            "study_uid": study_uid, "series_uid": series_uid}


def test_no_original_identifier_remains(study):
    for path in sorted(study["dst"].iterdir()):
        values = list(dump_values(pydicom.dcmread(path)))
        for original in ORIGINALS:
            assert not any(original in v for v in values), f"{original!r} found in tag dump"
    # And the same check on the raw bytes of the files (catches anything hidden).
    assert find_leaks(study["dst"], ORIGINALS) == []


def test_original_filenames_are_not_kept(study):
    names = sorted(p.name for p in study["dst"].iterdir())
    assert names == ["000001.dcm", "000002.dcm", "000003.dcm"]


def test_uids_are_regenerated_consistently(study):
    files = [pydicom.dcmread(p) for p in sorted(study["dst"].iterdir())]
    assert {f.StudyInstanceUID for f in files} != {study["study_uid"]}
    assert len({f.StudyInstanceUID for f in files}) == 1      # same study UID in all files
    assert len({f.SeriesInstanceUID for f in files}) == 1     # same series UID in all files
    assert len({f.SOPInstanceUID for f in files}) == 3        # but each image is unique
    for f in files:
        assert f.file_meta.MediaStorageSOPInstanceUID == f.SOPInstanceUID
        assert f.SOPClassUID == "1.2.840.10008.5.1.4.1.1.2"   # class UID must be kept


def test_private_tags_are_removed(study):
    for path in study["dst"].iterdir():
        assert not [e for e in all_tags(pydicom.dcmread(path)) if e.tag.is_private]


def test_medical_content_is_preserved(study):
    original = pydicom.dcmread(sorted(study["src"].iterdir())[0])
    anon = pydicom.dcmread(sorted(study["dst"].iterdir())[0])
    assert anon.Modality == "CT"
    assert anon.BodyPartExamined == "ABDOMEN"
    assert anon.PixelData == original.PixelData
    assert anon.PatientIdentityRemoved == "YES"


def test_key_replaces_identity_and_link_is_returned(study):
    result = study["result"]
    anon = pydicom.dcmread(sorted(study["dst"].iterdir())[0])
    assert anon.PatientID == result.study_key
    assert str(anon.PatientName) == result.study_key
    # The real identity is returned to the caller for the clinical key table only.
    assert result.patient_id == FAKE["patient_id"]
    assert result.patient_name == FAKE["name"]


def test_originals_can_be_deleted(tmp_path):
    src, dst = tmp_path / "raw", tmp_path / "anon"
    make_fake_study(src)
    anonymize_folder(src, dst, delete_originals=True)
    assert not src.exists()
    assert len(list(dst.iterdir())) == 3

"""Tests for the task selector: metadata checks and task detection."""
import pytest
from fastapi import HTTPException
from pydicom.uid import generate_uid

from app.routing import StudyInfo, check_task, detect_task, read_study_info
from tests.fake_dicom import make_fake_dicom, make_fake_study


def info(**changes):
    values = dict(file_count=3, modalities={"CT"}, body_parts={"ABDOMEN"},
                  series_count=1, study_count=1, patient_count=1, sequence="")
    values.update(changes)
    return StudyInfo(**values)


def error_code(task, study_info):
    with pytest.raises(HTTPException) as caught:
        check_task(task, study_info)
    return caught.value.detail["code"]


def test_liver_ct_accepts_a_ct_abdomen():
    assert check_task("liver_ct", info()) == []


def test_brain_mri_accepts_an_mr_head():
    assert check_task("brain_mri", info(modalities={"MR"}, body_parts={"HEAD"})) == []


def test_modality_mismatch_is_rejected():
    assert error_code("brain_mri", info()) == "MODALITY_MISMATCH"   # CT files, MRI task


def test_body_part_of_another_task_is_rejected():
    mr_abdomen = info(modalities={"MR"}, body_parts={"ABDOMEN"})
    assert error_code("brain_mri", mr_abdomen) == "BODY_PART_MISMATCH"


def test_missing_body_part_is_only_a_warning():
    assert len(check_task("liver_ct", info(body_parts=set()))) == 1


def test_multiple_series_are_rejected():
    assert error_code("liver_ct", info(series_count=2)) == "MULTIPLE_SERIES"


def test_unknown_task_is_rejected():
    assert error_code("chest_ct", info()) == "UNKNOWN_TASK"


def test_detect_task():
    assert detect_task(info()) == ("liver_ct", "high")
    assert detect_task(info(modalities={"MR"}, body_parts={"HEAD"})) == ("brain_mri", "high")
    assert detect_task(info(modalities={"MR"}, body_parts=set())) == ("brain_mri", "low")
    assert detect_task(info(modalities={"MR"}, body_parts={"ABDOMEN"})) == (None, "")


def test_read_study_info_from_real_files(tmp_path):
    make_fake_study(tmp_path / "study", slices=3)
    result = read_study_info(tmp_path / "study")
    assert result.file_count == 3
    assert result.modalities == {"CT"}
    assert result.series_count == 1 and result.patient_count == 1


def test_two_series_are_detected(tmp_path):
    study_uid = generate_uid()
    make_fake_dicom(tmp_path / "a.dcm", study_uid, generate_uid(), 1)
    make_fake_dicom(tmp_path / "b.dcm", study_uid, generate_uid(), 2)
    assert read_study_info(tmp_path).series_count == 2

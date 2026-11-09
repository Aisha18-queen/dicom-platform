"""DUMMY workers: they return FAKE results in the agreed JSON shape.

They exist so the whole flow (queue, statuses, result page) can be built and
tested before the real models arrive. Every answer carries "dummy": true, so
nobody can mistake it for a real analysis. The real functions (written by the
ML teammate) must return the same shape:

    run_brain_mri(input_dir, key) -> dict
    run_liver_ct(input_dir, output_dir, key) -> dict   (writes the DICOM-SEG into output_dir)
"""
from pathlib import Path

DISCLAIMER = "Research use only, not for clinical diagnosis"


def _count_slices(input_dir) -> int:
    return len(list(Path(input_dir).glob("*.dcm")))


def dummy_brain_mri(input_dir, key: str) -> dict:
    return {
        "key": key,
        "task": "brain_mri",
        "status": "success",
        "dummy": True,
        "model": {"name": "DUMMY (not a real model)", "version": "0"},
        "result": {
            "prediction": "meningioma",
            "confidence": 0.942,
            "probabilities": {"glioma": 0.038, "meningioma": 0.942, "notumor": 0.012, "pituitary": 0.008},
            "slices_used": _count_slices(input_dir),
            "aggregation": "mean_probability",
            "low_confidence": False,
        },
        "disclaimer": DISCLAIMER,
    }


def dummy_liver_ct(input_dir, output_dir, key: str) -> dict:
    return {
        "key": key,
        "task": "liver_ct",
        "status": "success",
        "dummy": True,
        "model": {"name": "DUMMY (not a real model)", "version": "0"},
        "result": {
            "volumes_ml": {"liver_ml": 1523.4, "tumor_ml": 42.1, "liver_minus_tumor_ml": 1481.3},
            "detection": {"tumor_detected": True, "num_tumor_components": 2, "largest_tumor_ml": 38.5},
            "metadata": {
                "input_shape": [512, 512, _count_slices(input_dir)],
                "input_spacing_mm": [0.78, 0.78, 2.5],
                "inference_time_sec": 0.0,
                "model_version": "dummy",
            },
            "seg_file": None,  # a real worker writes a DICOM-SEG into output_dir and returns its path here
        },
        "disclaimer": DISCLAIMER,
    }

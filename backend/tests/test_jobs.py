"""Tests for the job queue: statuses, results, the worker callback and the queue modes."""
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import jobs
from app.config import settings
from app.dummy_workers import dummy_brain_mri, dummy_liver_ct
from app.main import app
from tests.helpers import key_of, login, real_dicom_files

LIVER = {"task": "liver_ct"}


def worker_headers():
    return {"X-Worker-Secret": settings.worker_secret}


def success_payload(key, task="liver_ct"):
    return {"key": key, "task": task, "status": "success",
            "model": {"name": "test", "version": "1"},
            "result": {"detection": {"tumor_detected": False}},
            "disclaimer": "Research use only, not for clinical diagnosis"}


def upload(c, h, monkeypatch=None, mode=None):
    if mode:
        monkeypatch.setattr(settings, "queue_mode", mode)
    r = c.post("/studies", headers=h, data=LIVER, files=real_dicom_files(2))
    assert r.status_code == 201
    return r.json()


def test_local_queue_runs_the_dummy_worker_to_the_end():
    with TestClient(app) as c:
        h = login(c)
        body = upload(c, h)
        assert body["status"] == "queued"

        study = c.get(f"/studies/{body['study_id']}", headers=h).json()
        assert study["status"] == "done"          # the dummy worker has finished

        res = c.get(f"/studies/{body['study_id']}/result", headers=h).json()
        assert res["status"] == "done" and res["task"] == "liver_ct"
        assert res["dummy"] is True                # fake results are always labelled
        assert res["result"]["detection"]["tumor_detected"] is True
        assert res["disclaimer"].startswith("Research use only")
        assert "key" not in res                    # the random key is never shown to the frontend

        # The anonymized copy was removed from the hand-over area.
        assert not (Path(settings.transfer_dir) / key_of(body["study_id"]) / "input").exists()


def test_result_is_empty_while_the_queue_is_off(monkeypatch):
    with TestClient(app) as c:
        h = login(c)
        body = upload(c, h, monkeypatch, "off")
        assert body["status"] == "anonymized"
        res = c.get(f"/studies/{body['study_id']}/result", headers=h).json()
        assert res["status"] == "anonymized" and res["result"] is None and res["error"] is None


def test_worker_callback_stores_the_result(monkeypatch):
    with TestClient(app) as c:
        h = login(c)
        body = upload(c, h, monkeypatch, "off")
        key = key_of(body["study_id"])

        r = c.post("/internal/results", headers=worker_headers(), json=success_payload(key))
        assert r.status_code == 200 and r.json()["status"] == "done"

        res = c.get(f"/studies/{body['study_id']}/result", headers=h).json()
        assert res["status"] == "done"
        assert res["result"]["detection"]["tumor_detected"] is False

        # A second answer for the same job is refused.
        again = c.post("/internal/results", headers=worker_headers(), json=success_payload(key))
        assert again.status_code == 409


def test_worker_callback_needs_the_secret():
    with TestClient(app) as c:
        payload = success_payload("0" * 32)
        assert c.post("/internal/results", json=payload).status_code == 403
        wrong = c.post("/internal/results", headers={"X-Worker-Secret": "nope"}, json=payload)
        assert wrong.status_code == 403


def test_worker_error_marks_the_study_as_failed(monkeypatch):
    with TestClient(app) as c:
        h = login(c)
        body = upload(c, h, monkeypatch, "off")
        payload = {"key": key_of(body["study_id"]), "task": "liver_ct", "status": "error",
                   "error": {"code": "NO_LIVER_DETECTED", "message": "No liver found."}}
        assert c.post("/internal/results", headers=worker_headers(), json=payload).status_code == 200
        res = c.get(f"/studies/{body['study_id']}/result", headers=h).json()
        assert res["status"] == "failed"
        assert res["error"]["code"] == "NO_LIVER_DETECTED"
        assert res["result"] is None


def test_callback_rejects_a_result_for_another_task(monkeypatch):
    with TestClient(app) as c:
        h = login(c)
        body = upload(c, h, monkeypatch, "off")
        payload = success_payload(key_of(body["study_id"]), task="brain_mri")
        assert c.post("/internal/results", headers=worker_headers(), json=payload).status_code == 422


def test_callback_rejects_an_unknown_key():
    with TestClient(app) as c:
        r = c.post("/internal/results", headers=worker_headers(), json=success_payload("f" * 32))
        assert r.status_code == 404


def test_dummy_workers_have_the_agreed_shape(tmp_path):
    for i in range(3):
        (tmp_path / f"{i}.dcm").write_bytes(b"x")
    key = "a" * 32

    mri = dummy_brain_mri(tmp_path, key)
    assert mri["key"] == key and mri["task"] == "brain_mri" and mri["status"] == "success"
    assert mri["dummy"] is True
    assert abs(sum(mri["result"]["probabilities"].values()) - 1.0) < 1e-9
    assert mri["result"]["slices_used"] == 3
    assert mri["disclaimer"].startswith("Research use only")

    ct = dummy_liver_ct(tmp_path, tmp_path, key)
    assert ct["key"] == key and ct["task"] == "liver_ct" and ct["status"] == "success"
    assert "volumes_ml" in ct["result"] and "detection" in ct["result"]


def test_celery_mode_sends_the_job_to_the_queue_of_its_task(monkeypatch):
    sent = []
    fake_celery = SimpleNamespace(send_task=lambda name, args=None, queue=None, **kw: sent.append((name, args, queue)))
    monkeypatch.setattr(jobs, "_celery", lambda: fake_celery)
    with TestClient(app) as c:
        h = login(c)
        body = upload(c, h, monkeypatch, "celery")
        key = key_of(body["study_id"])
        assert body["status"] == "queued"
        assert sent == [("worker.run_job", [key, "liver_ct"], "liver_ct")]
        # The anonymized study was copied to the hand-over area, in a folder named by the key.
        assert len(list((Path(settings.transfer_dir) / key / "input").iterdir())) == 2


def test_queue_failure_marks_the_study_as_failed(monkeypatch):
    def broken():
        raise RuntimeError("Redis is down")
    monkeypatch.setattr(jobs, "_celery", broken)
    with TestClient(app) as c:
        h = login(c)
        body = upload(c, h, monkeypatch, "celery")
        assert body["status"] == "failed"
        res = c.get(f"/studies/{body['study_id']}/result", headers=h).json()
        assert res["error"]["code"] == "QUEUE_UNAVAILABLE"

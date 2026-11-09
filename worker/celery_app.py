import os

from celery import Celery

app = Celery(
    "worker",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    include=["worker.tasks"],
)
app.conf.task_acks_late = True            # a job is not lost if the worker crashes while running it
app.conf.worker_prefetch_multiplier = 1   # one job at a time (the models are heavy)

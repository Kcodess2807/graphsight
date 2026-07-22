"""Celery application: Redis broker + Beat schedule for the debounce sweeper.

Run a worker:   celery -A worker.celery_app worker --loglevel=info
Run the beat:   celery -A worker.celery_app beat   --loglevel=info
(Both from the backend/ directory.)
"""

from celery import Celery

from worker import settings

app = Celery(
    "tracerag",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["worker.tasks"],  # ensure task modules are imported by the worker
)

app.conf.update(
    task_default_queue="tracerag",
    task_acks_late=True,               # a compile that crashes mid-run is redelivered
    worker_prefetch_multiplier=1,      # compiles are heavy + long; don't hoard tasks
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
)

# Beat drives the debounce: every SWEEP_INTERVAL seconds it fires the sweeper,
# which claims any org whose window has closed and enqueues its reconcile.
app.conf.beat_schedule = {
    "sweep-due-reconciliations": {
        "task": "worker.tasks.sweep_due_reconciliations",
        "schedule": float(settings.SWEEP_INTERVAL),
    },
}

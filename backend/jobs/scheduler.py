"""Single-supervisor tick; heavy review preparation yields while a handler executes."""

from pathlib import Path

from backend.jobs.catchup import catch_up_reviews
from backend.jobs.queue import Queue
from backend.jobs.review_observation import observe_supervisor
from backend.portfolio.fills import enqueue_due_batches


def observation_grace(queue: Queue) -> int:
    return 2 * max(queue.limits.scheduler_tick_seconds, queue.limits.heartbeat_seconds)


def scheduler_tick(queue: Queue, root: Path, observer: str, *, include_reviews: bool) -> None:
    observe_supervisor(queue.engine, observer, observation_grace(queue))
    queue.catch_up(queue.limits.catchup_batch)
    enqueue_due_batches(queue)
    if include_reviews:
        catch_up_reviews(queue, root)

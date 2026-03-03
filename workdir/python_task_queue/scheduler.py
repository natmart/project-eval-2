"""
Simple scheduler implementation for the Python Task Queue Library.

Provides basic task scheduling functionality.
"""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger(__name__)


@dataclass
class ScheduledJob:
    """
    Represents a scheduled job.

    Attributes:
        id: Unique job identifier
        task_name: Name of the task to schedule
        payload: Task payload
        interval_seconds: Interval between executions in seconds
        last_run: Last execution timestamp
        next_run: Next scheduled execution timestamp
        enabled: Whether the job is enabled
    """
    id: int
    task_name: str
    payload: Optional[Any] = None
    interval_seconds: int = 60
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    enabled: bool = True


class CronScheduler:
    """
    Simple task scheduler.

    Supports interval-based task scheduling with a background thread.
    """

    def __init__(self, check_interval: float = 1.0):
        """
        Initialize the scheduler.

        Args:
            check_interval: How often to check for due jobs (seconds)
        """
        self.check_interval = check_interval
        self._jobs: Dict[int, ScheduledJob] = {}
        self._next_id = 1
        self._lock = threading.RLock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def add_job(
        self,
        task_name: str,
        payload: Optional[Any] = None,
        interval_seconds: int = 60,
    ) -> int:
        """
        Add a scheduled job.

        Args:
            task_name: Name of task to schedule
            payload: Task payload
            interval_seconds: Interval in seconds

        Returns:
            Job ID
        """
        with self._lock:
            job_id = self._next_id
            self._next_id += 1

            job = ScheduledJob(
                id=job_id,
                task_name=task_name,
                payload=payload,
                interval_seconds=interval_seconds,
                next_run=datetime.utcnow(),
            )

            self._jobs[job_id] = job
            logger.info(f"Added scheduled job {job_id} for task {task_name}")

            return job_id

    def remove_job(self, job_id: int) -> bool:
        """
        Remove a scheduled job.

        Args:
            job_id: Job ID

        Returns:
            True if removed, False if not found
        """
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                logger.info(f"Removed scheduled job {job_id}")
                return True
            return False

    def get_jobs(self) -> List[ScheduledJob]:
        """Get all scheduled jobs."""
        with self._lock:
            return list(self._jobs.values())

    def start(self) -> None:
        """Start the scheduler."""
        with self._lock:
            if self._running:
                logger.warning("Scheduler is already running")
                return

            self._running = True
            self._thread = threading.Thread(target=self._run_loop, name="CronScheduler", daemon=True)
            self._thread.start()
            logger.info("Scheduler started")

    def stop(self, timeout: float = 5.0) -> None:
        """
        Stop the scheduler.

        Args:
            timeout: Maximum time to wait for stop
        """
        with self._lock:
            if not self._running:
                logger.warning("Scheduler is not running")
                return

            self._running = False

        if self._thread:
            self._thread.join(timeout=timeout)
            logger.info("Scheduler stopped")

    def is_running(self) -> bool:
        """Check if scheduler is running."""
        with self._lock:
            return self._running

    def _run_loop(self) -> None:
        """Main scheduler loop."""
        logger.info("Scheduler loop started")

        while self._running:
            try:
                self._check_jobs()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)

        logger.info("Scheduler loop stopped")

    def _check_jobs(self) -> None:
        """Check for due jobs and process them."""
        now = datetime.utcnow()

        with self._lock:
            for job in self._jobs.values():
                if not job.enabled:
                    continue

                if job.next_run and job.next_run <= now:
                    self._execute_job(job)

    def _execute_job(self, job: ScheduledJob) -> None:
        """
        Execute a scheduled job.

        This base implementation just updates timestamps.
        Subclasses should override to actually enqueue tasks.
        """
        job.last_run = datetime.utcnow()
        job.next_run = datetime.utcnow().timestamp() + job.interval_seconds

        logger.info(
            f"Executed job {job.id} ({job.task_name}), "
            f"next run in {job.interval_seconds}s"
        )
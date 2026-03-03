"""
Cron scheduler for the Python Task Queue Library.

Provides task scheduling on cron-like patterns with background thread execution,
integration with task registry, and graceful shutdown support.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Pattern
from uuid import uuid4

from python_task_queue.models import Task, TaskStatus
from python_task_queue.registry import TaskRegistry, get_registry


logger = logging.getLogger(__name__)


# Type aliases
ScheduleExpression = str
TaskName = str
Payload = Any


class InvalidScheduleError(Exception):
    """Raised when a cron schedule expression is invalid."""
    pass


class SchedulerError(Exception):
    """Base exception for scheduler errors."""
    pass


class SchedulerNotRunningError(SchedulerError):
    """Raised when attempting to operate on a stopped scheduler."""
    pass


@dataclass
class ScheduledJob:
    """
    Represents a scheduled job.

    Attributes:
        id: Unique identifier for the job
        task_name: Name of the task to execute
        schedule: Cron schedule expression
        payload: Optional payload to pass to the task
        last_run: Timestamp of the last execution
        next_run: Timestamp of the next scheduled execution
        enabled: Whether the job is currently enabled
        metadata: Additional metadata about the job
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    task_name: str = ""
    schedule: str = ""
    payload: Optional[Any] = None
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"ScheduledJob(id={self.id[:8]}, task={self.task_name!r}, "
            f"schedule={self.schedule!r}, enabled={self.enabled})"
        )


class CronSchedule:
    """
    Parses and validates cron schedule expressions.

    Supports the standard cron format with 5 fields:
    minute hour day_of_month month day_of_week

    Examples:
        "* * * * *" - Every minute
        "*/5 * * * *" - Every 5 minutes
        "0 * * * *" - Every hour
        "0 0 * * *" - Every day at midnight
        "0 9 * * 1-5" - Every weekday at 9 AM
        "0 0 1 * *" - On the first day of every month
    """

    # Patterns for parsing each cron field
    FIELD_RANGES = {
        'minute': (0, 59),
        'hour': (0, 23),
        'day_of_month': (1, 31),
        'month': (1, 12),
        'day_of_week': (0, 6),  # 0 = Sunday, 6 = Saturday
    }

    DAY_NAMES = {
        'sun': 0, 'mon': 1, 'tue': 2, 'wed': 3,
        'thu': 4, 'fri': 5, 'sat': 6
    }

    MONTH_NAMES = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
        'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }

    def __init__(self, expression: str):
        """
        Initialize a cron schedule.

        Args:
            expression: Cron schedule expression (5 fields separated by spaces)

        Raises:
            InvalidScheduleError: If the expression is invalid
        """
        parts = expression.strip().split()

        if len(parts) != 5:
            raise InvalidScheduleError(
                f"Invalid cron expression: expected 5 fields, got {len(parts)}"
            )

        self.expression = expression
        self.minute = self._parse_field(parts[0], 'minute')
        self.hour = self._parse_field(parts[1], 'hour')
        self.day_of_month = self._parse_field(parts[2], 'day_of_month')
        self.month = self._parse_field(parts[3], 'month')
        self.day_of_week = self._parse_field(parts[4], 'day_of_week')

        logger.debug(f"Parsed cron schedule: {expression}")

    @classmethod
    def _parse_field(cls, field_str: str, field_name: str) -> List[int]:
        """
        Parse a single cron field.

        Args:
            field_str: The field string to parse
            field_name: Name of the field (for error messages)

        Returns:
            List of valid values for this field

        Raises:
            InvalidScheduleError: If the field is invalid
        """
        min_val, max_val = cls.FIELD_RANGES[field_name]
        values = []

        # Split by comma
        parts = field_str.split(',')

        for part in parts:
            part = part.strip().lower()

            # Handle ranges: 1-5
            if '-' in part and '/' not in part:
                start, end = part.split('-')
                start = cls._parse_value(start, field_name)
                end = cls._parse_value(end, field_name)
                values.extend(range(start, end + 1))

            # Handle step values: */5 or 1-10/2
            elif '/' in part:
                base_part, step = part.split('/')
                step = int(step)

                if base_part == '*':
                    values.extend(range(min_val, max_val + 1, step))
                elif '-' in base_part:
                    start, end = base_part.split('-')
                    start = cls._parse_value(start, field_name)
                    end = cls._parse_value(end, field_name)
                    values.extend(range(start, end + 1, step))
                else:
                    base = cls._parse_value(base_part, field_name)
                    values.extend(range(base, max_val + 1, step))

            # Handle wildcards: *
            elif part == '*':
                values.extend(range(min_val, max_val + 1))

            # Handle single value
            else:
                values.append(cls._parse_value(part, field_name))

        # Validate and deduplicate
        unique_values = []
        for val in sorted(set(values)):
            if not (min_val <= val <= max_val):
                raise InvalidScheduleError(
                    f"Invalid value {val} for field '{field_name}': "
                    f"must be between {min_val} and {max_val}"
                )
            unique_values.append(val)

        return unique_values

    @classmethod
    def _parse_value(cls, value_str: str, field_name: str) -> int:
        """
        Parse a single value, handling named days/months.

        Args:
            value_str: String value to parse
            field_name: Name of the field

        Returns:
            Integer value
        """
        value_str = value_str.strip().lower()
        value_str = value_str.lstrip('0')  # Remove leading zeros

        # Check for named days or months
        if field_name == 'day_of_week' and value_str in cls.DAY_NAMES:
            return cls.DAY_NAMES[value_str]
        elif field_name == 'month' and value_str in cls.MONTH_NAMES:
            return cls.MONTH_NAMES[value_str]

        # Parse as integer
        try:
            return int(value_str)
        except ValueError as e:
            raise InvalidScheduleError(
                f"Invalid value '{value_str}' for field '{field_name}'"
            ) from e

    def should_run(self, dt: datetime) -> bool:
        """
        Check if the schedule should run at the given datetime.

        Args:
            dt: Datetime to check against the schedule

        Returns:
            True if the schedule should run at this datetime
        """
        return (
            dt.minute in self.minute and
            dt.hour in self.hour and
            dt.day in self.day_of_month and
            dt.month in self.month and
            dt.weekday() in self.day_of_week
        )

    def next_run_time(self, from_time: Optional[datetime] = None) ->datetime:
        """
        Calculate the next time this schedule should run.

        Args:
            from_time: Start time for calculation (defaults to now)

        Returns:
            Datetime of the next scheduled run
        """
        if from_time is None:
            from_time = datetime.now()

        # Move to next minute to avoid running the same minute twice
        check_time = from_time + timedelta(minutes=1)
        check_time = check_time.replace(second=0, microsecond=0)

        # Look ahead up to 4 years (maximum needed for any schedule)
        max_checks = 4 * 365 * 24 * 60  # 4 years of minutes
        checks = 0

        while checks < max_checks:
            if self.should_run(check_time):
                return check_time

            check_time = check_time + timedelta(minutes=1)
            checks += 1

        raise SchedulerError(f"Could not find next run time for schedule: {self.expression}")

    def __repr__(self) -> str:
        return f"CronSchedule('{self.expression}')"


class CronScheduler:
    """
    Cron-based task scheduler.

    Schedules tasks to run on cron-like patterns in a background thread.
    Integrates with the task registry to execute registered tasks.

    Attributes:
        registry: Task registry to use for finding task handlers
        backend: Queue backend to enqueue tasks into
        jobs: Dictionary of scheduled jobs indexed by job ID
        _running: Whether the scheduler is running
        _thread: Background scheduling thread
        _stop_event: Event to signal graceful shutdown
        _interval: Sleep interval between schedule checks (seconds)
    """

    def __init__(
        self,
        registry: Optional[TaskRegistry] = None,
        backend: Optional[Any] = None,
        check_interval: float = 1.0
    ):
        """
        Initialize the cron scheduler.

        Args:
            registry: Task registry (defaults to global registry)
            backend: Queue backend for enqueuing tasks (optional)
            check_interval: Interval between schedule checks in seconds
        """
        self.registry = registry or get_registry()
        self.backend = backend
        self.check_interval = check_interval

        self.jobs: Dict[str, ScheduledJob] = {}
        self._lock = threading.RLock()

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        logger.info("CronScheduler initialized")

    def add_job(
        self,
        task_name: str,
        schedule: str,
        payload: Optional[Any] = None,
        job_id: Optional[str] = None,
        enabled: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ScheduledJob:
        """
        Add a scheduled job.

        Args:
            task_name: Name of the registered task to execute
            schedule: Cron schedule expression
            payload: Optional payload to pass to the task
            job_id: Optional custom job ID (auto-generated if not provided)
            enabled: Whether the job is initially enabled
            metadata: Optional metadata for the job

        Returns:
            The created ScheduledJob

        Raises:
            TaskNotFoundError: If the task is not registered
            InvalidScheduleError: If the schedule expression is invalid
        """
        # Validate task exists
        if not self.registry.contains(task_name):
            raise TaskNotFoundError(task_name)

        # Parse schedule
        cron_schedule = CronSchedule(schedule)

        # Calculate next run time
        next_run = cron_schedule.next_run_time()

        # Create job
        job = ScheduledJob(
            id=job_id or str(uuid4()),
            task_name=task_name,
            schedule=schedule,
            payload=payload,
            next_run=next_run,
            enabled=enabled,
            metadata=metadata or {}
        )

        # Store job
        with self._lock:
            self.jobs[job.id] = job

        logger.info(
            f"Added scheduled job: {job.id[:8]} for task '{task_name}' "
            f"with schedule '{schedule}' (next run: {next_run})"
        )

        return job

    def remove_job(self, job_id: str) -> None:
        """
        Remove a scheduled job.

        Args:
            job_id: ID of the job to remove

        Raises:
            KeyError: If the job doesn't exist
        """
        with self._lock:
            if job_id not in self.jobs:
                raise KeyError(f"Job {job_id} not found")
            job = self.jobs.pop(job_id)

        logger.info(f"Removed scheduled job: {job.id[:8]}")

    def get_job(self, job_id: str) -> Optional[ScheduledJob]:
        """
        Get a scheduled job by ID.

        Args:
            job_id: ID of the job

        Returns:
            The ScheduledJob, or None if not found
        """
        with self._lock:
            return self.jobs.get(job_id)

    def list_jobs(self, enabled_only: bool = False) -> List[ScheduledJob]:
        """
        List all scheduled jobs.

        Args:
            enabled_only: If True, only return enabled jobs

        Returns:
            List of ScheduledJob objects
        """
        with self._lock:
            jobs = list(self.jobs.values())
            if enabled_only:
                jobs = [j for j in jobs if j.enabled]
            return jobs

    def enable_job(self, job_id: str) -> None:
        """
        Enable a scheduled job.

        Args:
            job_id: ID of the job to enable

        Raises:
            KeyError: If the job doesn't exist
        """
        with self._lock:
            if job_id not in self.jobs:
                raise KeyError(f"Job {job_id} not found")
            self.jobs[job_id].enabled = True
            # Recalculate next run time
            cron = CronSchedule(self.jobs[job_id].schedule)
            self.jobs[job_id].next_run = cron.next_run_time()

        logger.debug(f"Enabled job: {job_id[:8]}")

    def disable_job(self, job_id: str) -> None:
        """
        Disable a scheduled job.

        Args:
            job_id: ID of the job to disable

        Raises:
            KeyError: If the job doesn't exist
        """
        with self._lock:
            if job_id not in self.jobs:
                raise KeyError(f"Job {job_id} not found")
            self.jobs[job_id].enabled = False

        logger.debug(f"Disabled job: {job_id[:8]}")

    def start(self) -> None:
        """
        Start the scheduler background thread.

        Raises:
            RuntimeError: If the scheduler is already running
        """
        if self._running:
            raise RuntimeError("Scheduler is already running")

        self._running = True
        self._stop_event.clear()

        # Initialize next run times for all jobs
        with self._lock:
            for job in self.jobs.values():
                if job.enabled and job.next_run is None:
                    cron = CronSchedule(job.schedule)
                    job.next_run = cron.next_run_time()

        # Start background thread
        self._thread = threading.Thread(
            target=self._run_loop,
            name="CronScheduler",
            daemon=True
        )
        self._thread.start()

        logger.info("CronScheduler started")

    def stop(self, timeout: Optional[float] = None) -> None:
        """
        Stop the scheduler gracefully.

        Args:
            timeout: Optional timeout in seconds to wait for shutdown

        Raises:
            SchedulerNotRunningError: If the scheduler is not running
        """
        if not self._running:
            raise SchedulerNotRunningError("Scheduler is not running")

        logger.info("Stopping CronScheduler...")

        # Signal stop
        self._stop_event.set()
        self._running = False

        # Wait for thread to finish
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(
                    f"CronScheduler thread did not stop within {timeout} seconds"
                )
            else:
                logger.info("CronScheduler stopped gracefully")

    def is_running(self) -> bool:
        """
        Check if the scheduler is running.

        Returns:
            True if the scheduler is running
        """
        return self._running

    def _run_loop(self) -> None:
        """
        Main scheduling loop (runs in background thread).

        Continuously checks for due jobs and enqueues them.
        """
        logger.debug("Scheduler loop started")

        while self._running and not self._stop_event.is_set():
            try:
                now = datetime.now()

                # Check for due jobs
                with self._lock:
                    for job in self.jobs.values():
                        if not job.enabled:
                            continue

                        if job.next_run and job.next_run <= now:
                            self._execute_job(job)

                # Sleep until next check or stop event
                self._stop_event.wait(self.check_interval)

            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                # Continue running despite errors

        logger.debug("Scheduler loop stopped")

    def _execute_job(self, job: ScheduledJob) -> None:
        """
        Execute a scheduled job.

        Args:
            job: The job to execute
        """
        try:
            logger.info(
                f"Executing scheduled job: {job.id[:8]} "
                f"(task: {job.task_name})"
            )

            # Create and enqueue task
            task = Task(
                name=job.task_name,
                payload=job.payload,
                priority=5,
                metadata=dict(job.metadata, job_id=job.id, scheduled=True)
            )

            # Enqueue to backend if available, otherwise just log
            if self.backend is not None:
                self.backend.enqueue(task)
                logger.info(
                    f"Enqueued task from job {job.id[:8]}: task.id={task.id}"
                )
            else:
                logger.warning(
                    f"No backend configured for scheduler. Task created but not enqueued: "
                    f"task.id={task.id}, task_name={task.name}"
                )

            # Update job timestamps
            job.last_run = datetime.now()
            cron = CronSchedule(job.schedule)
            job.next_run = cron.next_run_time()

            logger.debug(
                f"Job {job.id[:8]} completed. Next run: {job.next_run}"
            )

        except Exception as e:
            logger.error(
                f"Failed to execute job {job.id[:8]}: {e}",
                exc_info=True
            )
            # Still update next run time even on failure
            try:
                cron = CronSchedule(job.schedule)
                job.next_run = cron.next_run_time()
            except Exception:
                pass

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()

    def __repr__(self) -> str:
        return (
            f"CronScheduler(jobs={len(self.jobs)}, running={self._running})"
        )
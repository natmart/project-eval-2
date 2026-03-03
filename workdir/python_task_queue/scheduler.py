"""
Cron Scheduler implementation for the Python Task Queue Library.

This module provides a cron-based task scheduling system that allows tasks
to be scheduled at specific times or intervals using standard cron syntax.

Key components:
- CronSchedule: Parser for cron expressions and scheduler logic
- ScheduledJob: Dataclass representing a scheduled job
- CronScheduler: Main scheduler with background thread for job execution
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID, uuid4

import re
from threading import Thread, RLock, Event
import time


# Named day and month constants
NAMED_DAYS = {
    "sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6,
    "sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4, "friday": 5, "saturday": 6,
}

NAMED_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


class CronSchedule:
    """
    Parser and matcher for cron expressions.
    
    Supports standard 5-field cron expressions:
        minute hour day_of_month month day_of_week
    
    Field ranges:
        minute: 0-59
        hour: 0-23
        day_of_month: 1-31
        month: 1-12
        day_of_week: 0-6 (0=Sunday)
    
    Supported patterns:
        Wildcards: *
        Intervals: */n
        Ranges: n-m
        Lists: n,m,o
        Named days: Mon, Tue, etc.
        Named months: Jan, Feb, etc.
    """
    
    def __init__(self, expression: str):
        """
        Initialize CronSchedule with a cron expression.
        
        Args:
            expression: Cron expression string (5 fields, space-separated)
            
        Raises:
            ValueError: If the expression is invalid
        """
        self.expression = expression.strip().lower()
        self._parse_expression()
    
    def _parse_expression(self) -> None:
        """Parse the cron expression into field specifications."""
        fields = self.expression.split()
        if len(fields) != 5:
            raise ValueError(
                f"Cron expression must have exactly 5 fields, got {len(fields)}: {self.expression}"
            )
        
        # Parse each field
        self.minute_spec = self._parse_field(fields[0], 0, 59)
        self.hour_spec = self._parse_field(fields[1], 0, 23)
        self.day_of_month_spec = self._parse_field(fields[2], 1, 31)
        self.month_spec = self._parse_field(fields[3], 1, 12)
        self.day_of_week_spec = self._parse_field(
            fields[4], 0, 6, use_named_values=NAMED_DAYS
        )
    
    def _parse_field(
        self,
        field: str,
        min_val: int,
        max_val: int,
        use_named_values: Optional[Dict[str, int]] = None,
    ) -> List[int]:
        """Parse a single cron field specification."""
        values: List[int] = []
        
        # Handle named values
        if use_named_values:
            field = field.lower()
            for name, num in use_named_values.items():
                field = field.replace(name, str(num))
        
        # Handle comma-separated list
        parts = field.split(",")
        for part in parts:
            values.extend(self._parse_part(part, min_val, max_val))
        
        return sorted(list(set(values)))  # Remove duplicates and sort
    
    def _parse_part(self, part: str, min_val: int, max_val: int) -> List[int]:
        """Parse a single part of a field (could be *, n, n-m, */n)."""
        part = part.strip()
        
        # Wildcard
        if part == "*":
            return list(range(min_val, max_val + 1))
        
        # Interval with wildcard */n
        if part.startswith("*/"):
            interval = int(part[2:])
            return list(range(min_val, max_val + 1, interval))
        
        # Range n-m
        if "-" in part:
            start, end = part.split("-")
            start = int(start.strip())
            end = int(end.strip())
            return list(range(start, end + 1))
        
        # Range with interval n-m/o
        if "/" in part and "-" in part:
            range_part, interval = part.split("/")
            start, end = range_part.split("-")
            start = int(start.strip())
            end = int(end.strip())
            interval = int(interval.strip())
            return list(range(start, end + 1, interval))
        
        # Interval with single value n/o
        if "/" in part:
            value, interval = part.split("/")
            value = int(value.strip())
            interval = int(interval.strip())
            return list(range(value, max_val + 1, interval))
        
        # Single value
        value = int(part)
        if not min_val <= value <= max_val:
            raise ValueError(f"Value {value} not in range {min_val}-{max_val}")
        return [value]
    
    def should_run(self, timestamp: datetime) -> bool:
        """
        Check if the schedule should run at the given timestamp.
        
        Args:
            timestamp: The datetime to check
            
        Returns:
            True if the schedule should run at this timestamp
        """
        return (
            timestamp.minute in self.minute_spec
            and timestamp.hour in self.hour_spec
            and timestamp.day in self.day_of_month_spec
            and timestamp.month in self.month_spec
            and timestamp.weekday() in self.day_of_week_spec
        )
    
    def next_run_time(self, after: Optional[datetime] = None) -> datetime:
        """
        Calculate the next time this schedule should run.
        
        Args:
            after: If provided, find the next run after this time
            
        Returns:
            datetime of the next scheduled run
        """
        if after is None:
            after = datetime.utcnow()
        
        # Check current second, move to next minute if needed
        if after.second > 0:
            after = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        else:
            after = after.replace(second=0, microsecond=0)
        
        # Search minute by minute (simple but not most efficient)
        max_iterations = 366 * 24 * 60  # Maximum one year ahead
        count = 0
        check_time = after
        
        while count < max_iterations:
            if self.should_run(check_time):
                return check_time
            
            # Move forward one minute
            check_time += timedelta(minutes=1)
            count += 1
        
        raise ValueError("Could not find next run time within one year")
    
    def matches_minute(self, minute: int) -> bool:
        """Check if a minute matches this schedule."""
        return minute in self.minute_spec
    
    def matches_hour(self, hour: int) -> bool:
        """Check if an hour matches this schedule."""
        return hour in self.hour_spec
    
    def matches_day(self, day: int) -> bool:
        """Check if a day of month matches this schedule."""
        return day in self.day_of_month_spec
    
    def matches_month(self, month: int) -> bool:
        """Check if a month matches this schedule."""
        return month in self.month_spec
    
    def matches_weekday(self, weekday: int) -> bool:
        """Check if a day of week matches this schedule."""
        return weekday in self.day_of_week_spec


@dataclass
class ScheduledJob:
    """
    Represents a scheduled job in the scheduler.
    
    Attributes:
        id: Unique identifier for the job
        task_name: Name of the task to execute
        schedule: CronSchedule defining when to run
        payload: Payload to pass to the task when executed
        enabled: Whether the job is currently enabled
        last_run: Timestamp of the last execution (None if never run)
        next_run: Timestamp of the next scheduled execution
        metadata: Additional metadata for the job
    """
    
    id: UUID = field(default_factory=uuid4)
    task_name: str = ""
    schedule: Optional[CronSchedule] = None
    payload: Optional[Dict[str, Any]] = None
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def update_next_run(self, after: Optional[datetime] = None) -> None:
        """Update the next run time based on the schedule."""
        if self.schedule:
            self.next_run = self.schedule.next_run_time(after)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        if data.get("schedule"):
            data["schedule"] = self.schedule.expression if self.schedule else None
        data["id"] = str(self.id)
        if data.get("last_run"):
            data["last_run"] = self.last_run.isoformat()  # type: ignore
        if data.get("next_run"):
            data["next_run"] = self.next_run.isoformat()  # type: ignore
        return data


class CronScheduler:
    """
    Cron-based task scheduler.
    
    Runs a background thread that periodically checks for jobs whose
    cron schedule matches the current time and enqueues them for execution.
    
    Thread-safe operations using RLock.
    """
    
    DEFAULT_CHECK_INTERVAL = 1  # seconds
    
    def __init__(
        self,
        check_interval: float = DEFAULT_CHECK_INTERVAL,
        task_registry: Optional[Any] = None,
        queue_backend: Optional[Any] = None,
    ):
        """
        Initialize the CronScheduler.
        
        Args:
            check_interval: How often (in seconds) to check for jobs to run (default: 1)
            task_registry: Optional task registry for looking up tasks
            queue_backend: Optional queue backend for enqueuing tasks
        """
        self.check_interval = check_interval
        self.task_registry = task_registry
        self.queue_backend = queue_backend
        
        self._jobs: Dict[UUID, ScheduledJob] = {}
        self._lock = RLock()
        
        self._thread: Optional[Thread] = None
        self._stop_event = Event()
        self._running = False
    
    def add_job(
        self,
        task_name: str,
        cron_expression: str,
        payload: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ScheduledJob:
        """
        Add a job to the scheduler.
        
        Args:
            task_name: Name of the task to execute
            cron_expression: Cron expression for scheduling
            payload: Payload to pass to the task
            enabled: Whether the job should start enabled
            metadata: Additional metadata
            
        Returns:
            The created ScheduledJob
        """
        schedule = CronSchedule(cron_expression)
        
        job = ScheduledJob(
            task_name=task_name,
            schedule=schedule,
            payload=payload,
            enabled=enabled,
            metadata=metadata or {},
        )
        
        # Calculate next run time
        if enabled:
            job.update_next_run()
        
        with self._lock:
            self._jobs[job.id] = job
        
        return job
    
    def remove_job(self, job_id: UUID) -> bool:
        """
        Remove a job from the scheduler.
        
        Args:
            job_id: UUID of the job to remove
            
        Returns:
            True if job was found and removed
        """
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                return True
            return False
    
    def get_job(self, job_id: UUID) -> Optional[ScheduledJob]:
        """Get a job by ID."""
        with self._lock:
            return self._jobs.get(job_id)
    
    def get_all_jobs(self) -> List[ScheduledJob]:
        """Get all jobs."""
        with self._lock:
            return list(self._jobs.values())
    
    def get_enabled_jobs(self) -> List[ScheduledJob]:
        """Get only enabled jobs."""
        with self._lock:
            return [job for job in self._jobs.values() if job.enabled]
    
    def enable_job(self, job_id: UUID) -> Optional[ScheduledJob]:
        """Enable a job (if not already enabled)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job and not job.enabled:
                job.enabled = True
                job.update_next_run()
            return job
    
    def disable_job(self, job_id: UUID) -> Optional[ScheduledJob]:
        """Disable a job (if currently enabled)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.enabled:
                job.enabled = False
                job.next_run = None
            return job
    
    def update_job_schedule(
        self,
        job_id: UUID,
        cron_expression: str,
    ) -> Optional[ScheduledJob]:
        """
        Update a job's schedule.
        
        Args:
            job_id: UUID of the job
            cron_expression: New cron expression
            
        Returns:
            The updated job, or None if not found
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            
            job.schedule = CronSchedule(cron_expression)
            if job.enabled:
                job.update_next_run()
            
            return job
    
    def clear_jobs(self) -> None:
        """Remove all jobs from the scheduler."""
        with self._lock:
            self._jobs.clear()
    
    def job_count(self) -> int:
        """Get the total number of jobs."""
        with self._lock:
            return len(self._jobs)
    
    def start(self) -> None:
        """Start the background scheduler thread."""
        if self._running:
            return
        
        self._stop_event.clear()
        self._running = True
        self._thread = Thread(target=self._run_loop, daemon=True)
        self._thread.start()
    
    def stop(self, timeout: Optional[float] = None) -> None:
        """
        Stop the background scheduler thread.
        
        Args:
            timeout: Maximum time to wait for thread to stop (None = wait indefinitely)
        """
        if not self._running:
            return
        
        self._stop_event.set()
        self._running = False
        
        if self._thread:
            self._thread.join(timeout=timeout)
    
    def is_running(self) -> bool:
        """Check if the scheduler is currently running."""
        return self._running
    
    def _run_loop(self) -> None:
        """Main loop for the background scheduler thread."""
        while not self._stop_event.is_set():
            try:
                self._check_and_run_jobs()
            except Exception:
                # Log error but continue running
                pass
            
            # Wait for check interval or stop event
            self._stop_event.wait(timeout=self.check_interval)
    
    def _check_and_run_jobs(self) -> List[UUID]:
        """
        Check for jobs that need to run and execute them.
        
        Returns:
            List of job IDs that were run
        """
        now = datetime.utcnow()
        run_jobs: List[UUID] = []
        
        with self._lock:
            for job_id, job in self._jobs.items():
                if not job.enabled:
                    continue
                
                if not job.next_run:
                    continue
                
                # Check if the job should run now
                if job.next_run <= now and job.schedule and job.schedule.should_run(now):
                    try:
                        self._execute_job(job)
                        job.last_run = now
                        job.update_next_run(after=now)
                        run_jobs.append(job_id)
                    except Exception:
                        # Update next run even on failure to prevent repeated failures
                        job.update_next_run(after=now + timedelta(minutes=1))
        
        return run_jobs
    
    def _execute_job(self, job: ScheduledJob) -> None:
        """
        Execute a scheduled job.
        
        If task registry and queue backend are configured, enqueues the task.
        Otherwise, this is a no-op (subclass can override).
        
        Args:
            job: The job to execute
        """
        # Base implementation: if we have registry and backend, enqueue the task
        # This can be overridden or extended for custom execution
        if self.task_registry and self.queue_backend:
            # Note: In a full implementation, this would enqueue the task
            # For now, this is a placeholder that would integrate with the queue
            pass
    
    def __enter__(self):
        """Context manager entry - start scheduler."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - stop scheduler."""
        self.stop()
        return False
    
    def get_due_jobs(self) -> List[ScheduledJob]:
        """
        Get jobs that are due to run at the current moment.
        
        Returns:
            List of jobs that should run now
        """
        now = datetime.utcnow()
        with self._lock:
            return [
                job
                for job in self._jobs.values()
                if job.enabled
                and job.next_run
                and job.next_run <= now
                and job.schedule
                and job.schedule.should_run(now)
            ]
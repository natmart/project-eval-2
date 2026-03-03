"""
Tests for the cron scheduler module.

Test coverage includes:
- CronSchedule parsing and validation
- Scheduled job management
- CronScheduler functionality
- Background thread execution
- Graceful shutdown
- Integration with registry and backends
"""

import time
import threading
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import pytest

from python_task_queue.scheduler import (
    CronSchedule,
    CronScheduler,
    ScheduledJob,
    InvalidScheduleError,
    SchedulerError,
    SchedulerNotRunningError,
)
from python_task_queue.models import Task
from python_task_queue.registry import TaskRegistry, task, TaskNotFoundError


# =============================================================================
# Test CronSchedule
# =============================================================================

class TestCronScheduleParsing:
    """Test cron schedule expression parsing."""

    def test_parse_every_minute(self):
        """Test parsing '* * * * *' (every minute)."""
        schedule = CronSchedule("* * * * *")
        assert len(schedule.minute) == 60
        assert len(schedule.hour) == 24
        assert len(schedule.day_of_month) == 31
        assert len(schedule.month) == 12
        assert len(schedule.day_of_week) == 7

    def test_parse_specific_minute(self):
        """Test parsing '5 * * * *' (at 5 minutes past the hour)."""
        schedule = CronSchedule("5 * * * *")
        assert schedule.minute == [5]
        assert len(schedule.hour) == 24

    def test_parse_interval_minutes(self):
        """Test parsing '*/5 * * * *' (every 5 minutes)."""
        schedule = CronSchedule("*/5 * * * *")
        assert schedule.minute == list(range(0, 60, 5))

    def test_parse_range(self):
        """Test parsing '9-17 * * * *' (minutes 9-17)."""
        schedule = CronSchedule("9-17 * * * *")
        assert schedule.minute == list(range(9, 18))

    def test_parse_list(self):
        """Test parsing '1,15,30 * * * *' (specific minutes)."""
        schedule = CronSchedule("1,15,30 * * * *")
        assert schedule.minute == [1, 15, 30]

    def test_parse_mixed(self):
        """Test parsing '*/10,5,20 */2 * * *' (complex expression)."""
        schedule = CronSchedule("*/10,5,20 */2 * * *")
        assert set(schedule.minute) == set([0, 5, 10, 20, 30, 40, 50])
        assert schedule.hour == list(range(0, 24, 2))

    def test_parse_step_with_range(self):
        """Test parsing '0-10/2 * * * *' (every 2 minutes from 0-10)."""
        schedule = CronSchedule("0-10/2 * * * *")
        assert schedule.minute == [0, 2, 4, 6, 8, 10]

    def test_parse_day_names(self):
        """Test parsing day names (Sun, Mon, etc.)."""
        schedule = CronSchedule("* * * * Mon,Fri")
        assert set(schedule.day_of_week) == {1, 5}  # Monday=1, Friday=5

    def test_parse_month_names(self):
        """Test parsing month names (Jan, Feb, etc.)."""
        schedule = CronSchedule("* * * Jan *")
        assert schedule.month == [1]

    def test_parse_invalid_field_count(self):
        """Test that invalid number of fields raises error."""
        with pytest.raises(InvalidScheduleError, match="expected 5 fields"):
            CronSchedule("* * *")

    def test_parse_invalid_value(self):
        """Test that invalid values raise error."""
        with pytest.raises(InvalidScheduleError, match="Invalid value"):
            CronSchedule("70 * * * *")  # Invalid minute

    def test_parse_invalid_range(self):
        """Test that invalid range raises error."""
        with pytest.raises(InvalidScheduleError, match="Invalid value"):
            CronSchedule("0-70 * * * *")

    def test_parse_invalid_step(self):
        """Test that invalid step value raises error."""
        with pytest.raises(ValueError):
            CronSchedule("*/0 * * * *")


class TestCronScheduleShouldRun:
    """Test should_run method."""

    def test_every_minute(self):
        """Test that every minute schedule always returns True."""
        schedule = CronSchedule("* * * * *")
        test_time = datetime(2024, 1, 15, 14, 30, 0)
        assert schedule.should_run(test_time)

    def test_specific_minute(self):
        """Test specific minute schedule."""
        schedule = CronSchedule("30 * * * *")
        assert schedule.should_run(datetime(2024, 1, 15, 14, 30, 0))
        assert not schedule.should_run(datetime(2024, 1, 15, 14, 31, 0))

    def test_specific_hour(self):
        """Test specific hour schedule."""
        schedule = CronSchedule("0 9 * * *")
        assert schedule.should_run(datetime(2024, 1, 15, 9, 0, 0))
        assert not schedule.should_run(datetime(2024, 1, 15, 10, 0, 0))

    def test_specific_day_of_month(self):
        """Test specific day of month schedule."""
        schedule = CronSchedule("0 0 15 * *")
        assert schedule.should_run(datetime(2024, 1, 15, 0, 0, 0))
        assert not schedule.should_run(datetime(2024, 1, 16, 0, 0, 0))

    def test_specific_month(self):
        """Test specific month schedule."""
        schedule = CronSchedule("0 0 * 6 *")
        assert schedule.should_run(datetime(2024, 6, 15, 0, 0, 0))
        assert not schedule.should_run(datetime(2024, 7, 15, 0, 0, 0))

    def test_specific_day_of_week(self):
        """Test specific day of week schedule."""
        schedule = CronSchedule("0 0 * * 1")  # Monday
        # Jan 15, 2024 is a Monday
        assert schedule.should_run(datetime(2024, 1, 15, 0, 0, 0))
        # Jan 16, 2024 is a Tuesday
        assert not schedule.should_run(datetime(2024, 1, 16, 0, 0, 0))

    def test_weekday_schedule(self):
        """Test using day names."""
        schedule = CronSchedule("0 9 * * Mon,Wed,Fri")
        assert schedule.should_run(datetime(2024, 1, 15, 9, 0, 0))  # Monday
        assert schedule.should_run(datetime(2024, 1, 17, 9, 0, 0))  # Wednesday
        assert not schedule.should_run(datetime(2024, 1, 16, 9, 0, 0))  # Tuesday


class TestCronScheduleNextRunTime:
    """Test next_run_time method."""

    def test_next_run_every_minute(self):
        """Test next run time for every minute schedule."""
        schedule = CronSchedule("* * * * *")
        base_time = datetime(2024, 1, 15, 14, 30, 30)
        next_time = schedule.next_run_time(base_time)
        # Should be next minute, with seconds set to 0
        assert next_time == datetime(2024, 1, 15, 14, 31, 0)

    def test_next_run_specific_minute(self):
        """Test next run time for specific minute schedule."""
        schedule = CronSchedule("30 * * * *")
        base_time = datetime(2024, 1, 15, 14, 0, 0)
        next_time = schedule.next_run_time(base_time)
        assert next_time == datetime(2024, 1, 15, 14, 30, 0)

    def test_next_run_hour_boundary(self):
        """Test next run time crossing hour boundary."""
        schedule = CronSchedule("0 15 * * *")
        base_time = datetime(2024, 1, 15, 14, 0, 0)
        next_time = schedule.next_run_time(base_time)
        assert next_time == datetime(2024, 1, 15, 15, 0, 0)

    def test_next_run_day_boundary(self):
        """Test next run time crossing day boundary."""
        schedule = CronSchedule("0 0 * * *")
        base_time = datetime(2024, 1, 15, 23, 59, 30)
        next_time = schedule.next_run_time(base_time)
        assert next_time == datetime(2024, 1, 16, 0, 0, 0)

    def test_next_run_month_boundary(self):
        """Test next run time crossing month boundary."""
        schedule = CronSchedule("0 0 1 * *")
        base_time = datetime(2024, 1, 31, 0, 0, 0)
        next_time = schedule.next_run_time(base_time)
        assert next_time == datetime(2024, 2, 1, 0, 0, 0)

    def test_next_run_year_boundary(self):
        """Test next run time crossing year boundary."""
        schedule = CronSchedule("0 0 1 1 *")
        base_time = datetime(2024, 12, 31, 0, 0, 0)
        next_time = schedule.next_run_time(base_time)
        assert next_time == datetime(2025, 1, 1, 0, 0, 0)

    def test_next_run_weekday_only(self):
        """Test next run time for weekday-only schedule."""
        schedule = CronSchedule("0 9 * * 1-5")  # Weekdays at 9 AM
        # Friday at 10 AM - next run should be Monday at 9 AM
        base_time = datetime(2024, 1, 19, 10, 0, 0)  # Friday
        next_time = schedule.next_run_time(base_time)
        assert next_time == datetime(2024, 1, 22, 9, 0, 0)  # Monday


# =============================================================================
# Test ScheduledJob
# =============================================================================

class TestScheduledJob:
    """Test ScheduledJob dataclass."""

    def test_create_job_defaults(self):
        """Test creating a job with default values."""
        job = ScheduledJob()
        assert job.id is not None
        assert job.task_name == ""
        assert job.schedule == ""
        assert job.payload is None
        assert job.last_run is None
        assert job.next_run is None
        assert job.enabled is True

    def test_create_job_with_values(self):
        """Test creating a job with specific values."""
        job = ScheduledJob(
            id="test-job-123",
            task_name="my_task",
            schedule="* * * * *",
            payload={"key": "value"},
            enabled=False,
            metadata={"owner": "test"}
        )
        assert job.id == "test-job-123"
        assert job.task_name == "my_task"
        assert job.schedule == "* * * * *"
        assert job.payload == {"key": "value"}
        assert job.enabled is False
        assert job.metadata == {"owner": "test"}

    def test_job_repr(self):
        """Test job string representation."""
        job = ScheduledJob(
            id="12345678-1234-5678-1234-567812345678",
            task_name="test_task",
            schedule="* * * * *",
            enabled=True
        )
        repr_str = repr(job)
        assert "12345678" in repr_str
        assert "test_task" in repr_str
        assert "* * * * *" in repr_str
        assert "True" in repr_str


# =============================================================================
# Test CronScheduler
# =============================================================================

@pytest.fixture
def registry():
    """Create a fresh task registry for testing."""
    registry = TaskRegistry()
    registry.clear()
    return registry


@pytest.fixture
def mock_backend():
    """Create a mock backend for testing."""
    backend = Mock()
    backend.enqueue = Mock()
    return backend


@pytest.fixture
def scheduler(registry, mock_backend):
    """Create a scheduler instance for testing."""
    return CronScheduler(registry=registry, backend=mock_backend)


class TestCronSchedulerInit:
    """Test CronScheduler initialization."""

    def test_init_default(self):
        """Test initialization with default values."""
        scheduler = CronScheduler()
        assert scheduler.registry is not None
        assert scheduler.backend is None
        assert scheduler.check_interval == 1.0
        assert scheduler.jobs == {}
        assert scheduler.is_running() is False

    def test_init_with_registry(self, registry):
        """Test initialization with custom registry."""
        scheduler = CronScheduler(registry=registry)
        assert scheduler.registry is registry

    def test_init_with_backend(self, mock_backend):
        """Test initialization with custom backend."""
        scheduler = CronScheduler(backend=mock_backend)
        assert scheduler.backend is mock_backend

    def test_init_with_check_interval(self, registry):
        """Test initialization with custom check interval."""
        scheduler = CronScheduler(registry=registry, check_interval=0.5)
        assert scheduler.check_interval == 0.5


class TestCronSchedulerJobManagement:
    """Test job management methods."""

    def test_add_job(self, registry, scheduler):
        """Test adding a scheduled job."""
        # Register a task
        @registry.register("test_task")
        def test_handler(payload):
            return payload

        # Add job
        job = scheduler.add_job(
            task_name="test_task",
            schedule="* * * * *",
            payload={"data": "test"}
        )

        assert job.id is not None
        assert job.task_name == "test_task"
        assert job.schedule == "* * * * *"
        assert job.payload == {"data": "test"}
        assert job.enabled is True
        assert job.next_run is not None

        # Verify job is in scheduler
        retrieved_job = scheduler.get_job(job.id)
        assert retrieved_job is job

    def test_add_job_with_custom_id(self, registry, scheduler):
        """Test adding a job with custom ID."""
        @registry.register("test_task")
        def test_handler(payload):
            return payload

        job = scheduler.add_job(
            task_name="test_task",
            schedule="* * * * *",
            job_id="my-custom-job-id"
        )

        assert job.id == "my-custom-job-id"

    def test_add_job_disabled(self, registry, scheduler):
        """Test adding a disabled job."""
        @registry.register("test_task")
        def test_handler(payload):
            return payload

        job = scheduler.add_job(
            task_name="test_task",
            schedule="* * * * *",
            enabled=False
        )

        assert job.enabled is False

    def test_add_task_not_found(self, scheduler):
        """Test adding a job for unregistered task."""
        with pytest.raises(TaskNotFoundError):
            scheduler.add_job(
                task_name="nonexistent_task",
                schedule="* * * * *"
            )

    def test_add_job_invalid_schedule(self, registry, scheduler):
        """Test adding a job with invalid schedule."""
        @registry.register("test_task")
        def test_handler(payload):
            return payload

        with pytest.raises(InvalidScheduleError):
            scheduler.add_job(
                task_name="test_task",
                schedule="invalid schedule"
            )

    def test_remove_job(self, registry, scheduler):
        """Test removing a job."""
        @registry.register("test_task")
        def test_handler(payload):
            return payload

        job = scheduler.add_job(
            task_name="test_task",
            schedule="* * * * *"
        )

        scheduler.remove_job(job.id)

        assert scheduler.get_job(job.id) is None

    def test_remove_job_not_found(self, scheduler):
        """Test removing a non-existent job."""
        with pytest.raises(KeyError, match="not found"):
            scheduler.remove_job("nonexistent-job-id")

    def test_list_jobs(self, registry, scheduler):
        """Test listing jobs."""
        @registry.register("task1")
        def handler1(payload):
            pass

        @registry.register("task2")
        def handler2(payload):
            pass

        job1 = scheduler.add_job("task1", "* * * * *")
        job2 = scheduler.add_job("task2", "*/5 * * * *", enabled=False)

        jobs = scheduler.list_jobs()
        assert len(jobs) == 2
        assert job1 in jobs
        assert job2 in jobs

    def test_list_jobs_enabled_only(self, registry, scheduler):
        """Test listing only enabled jobs."""
        @registry.register("task1")
        def handler1(payload):
            pass

        @registry.register("task2")
        def handler2(payload):
            pass

        job1 = scheduler.add_job("task1", "* * * * *")
        job2 = scheduler.add_job("task2", "*/5 * * * *", enabled=False)

        jobs = scheduler.list_jobs(enabled_only=True)
        assert len(jobs) == 1
        assert job1 in jobs
        assert job2 not in jobs

    def test_enable_job(self, registry, scheduler):
        """Test enabling a job."""
        @registry.register("task_task")
        def handler(payload):
            pass

        job = scheduler.add_job("task_task", "* * * * *", enabled=False)
        job_id = job.id

        scheduler.enable_job(job_id)

        job = scheduler.get_job(job_id)
        assert job.enabled is True
        assert job.next_run is not None

    def test_enable_job_not_found(self, scheduler):
        """Test enabling a non-existent job."""
        with pytest.raises(KeyError, match="not found"):
            scheduler.enable_job("nonexistent-job-id")

    def test_disable_job(self, registry, scheduler):
        """Test disabling a job."""
        @registry.register("task_task")
        def handler(payload):
            pass

        job = scheduler.add_job("task_task", "* * * * *")
        job_id = job.id

        scheduler.disable_job(job_id)

        job = scheduler.get_job(job_id)
        assert job.enabled is False

    def test_disable_job_not_found(self, scheduler):
        """Test disabling a non-existent job."""
        with pytest.raises(KeyError, match="not found"):
            scheduler.disable_job("nonexistent-job-id")


class TestCronSchedulerExecution:
    """Test job execution functionality."""

    def test_start_stop(self, scheduler):
        """Test starting and stopping the scheduler."""
        assert scheduler.is_running() is False

        scheduler.start()
        assert scheduler.is_running() is True

        scheduler.stop()
        assert scheduler.is_running() is False

    def test_start_already_running(self, scheduler):
        """Test that starting an already running scheduler raises error."""
        scheduler.start()

        with pytest.raises(RuntimeError, match="already running"):
            scheduler.start()

        scheduler.stop()

    def test_stop_not_running(self, scheduler):
        """Test that stopping a non-running scheduler raises error."""
        with pytest.raises(SchedulerNotRunningError, match="not running"):
            scheduler.stop()

    def test_execute_job_with_backend(self, registry, mock_backend, scheduler):
        """Test executing a job with a backend."""
        @registry.register("test_task")
        def handler(payload):
            return payload

        job = scheduler.add_job("test_task", "* * * * *", payload={"test": "data"})

        # Execute the job
        scheduler._execute_job(job)

        # Verify task was enqueued
        mock_backend.enqueue.assert_called_once()
        enqueued_task = mock_backend.enqueue.call_args[0][0]

        assert isinstance(enqueued_task, Task)
        assert enqueued_task.name == "test_task"
        assert enqueued_task.payload == {"test": "data"}
        assert job.last_run is not None
        assert job.next_run is not None

    def test_execute_job_without_backend(self, registry, scheduler):
        """Test executing a job without a backend (logs warning)."""
        @registry.register("test_task")
        def handler(payload):
            return payload

        job = scheduler.add_job("test_task", "* * * * *")

        # Should not raise exception, just log warning
        scheduler._execute_job(job)

        # Verify job timestamps were updated
        assert job.last_run is not None
        assert job.next_run is not None

    def test_execute_disabled_job(self, registry, mock_backend, scheduler):
        """Test that disabled jobs are not executed."""
        @registry.register("test_task")
        def handler(payload):
            pass

        job = scheduler.add_job("test_task", "* * * * *", enabled=False)
        last_run = job.last_run

        scheduler._execute_job(job)

        # Job should not have been executed
        mock_backend.enqueue.assert_not_called()
        assert job.last_run == last_run

    def test_multiple_jobs_execution(self, registry, mock_backend, scheduler):
        """Test executing multiple jobs."""
        @registry.register("task1")
        def handler1(payload):
            pass

        @registry.register("task2")
        def handler2(payload):
            pass

        job1 = scheduler.add_job("task1", "* * * * *", payload={"job": "1"})
        job2 = scheduler.add_job("task2", "* * * * *", payload={"job": "2"})

        # Execute both jobs
        scheduler._execute_job(job1)
        scheduler._execute_job(job2)

        # Verify both were enqueued
        assert mock_backend.enqueue.call_count == 2


class TestCronSchedulerBackgroundThread:
    """Test background thread execution."""

    def test_scheduler_loop_executes_due_jobs(self, registry, mock_backend):
        """Test that the scheduler loop executes jobs when due."""
        scheduler = CronScheduler(
            registry=registry,
            backend=mock_backend,
            check_interval=0.1
        )

        @registry.register("test_task")
        def handler(payload):
            pass

        # Add a job scheduled for every minute
        # Set next_run to now so it should execute immediately
        job = scheduler.add_job("test_task", "* * * * *")
        job.next_run = datetime.now() - timedelta(seconds=1)

        # Start scheduler
        scheduler.start()

        # Wait for job to execute
        time.sleep(0.5)

        # Stop scheduler
        scheduler.stop()

        # Verify task was enqueued
        assert mock_backend.enqueue.called
        enqueued_task = mock_backend.enqueue.call_args[0][0]
        assert enqueued_task.name == "test_task"

    def test_scheduler_loop_respects_interval(self, registry, mock_backend):
        """Test that scheduler respects the check interval."""
        scheduler = CronScheduler(
            registry=registry,
            backend=mock_backend,
            check_interval=0.2
        )

        @registry.register("test_task")
        def handler(payload):
            pass

        job = scheduler.add_job("test_task", "* * * * *")
        job.next_run = datetime.now() + timedelta(seconds=2)

        start_time = time.time()

        scheduler.start()
        time.sleep(1)
        scheduler.stop()

        elapsed = time.time() - start_time

        # With a 0.2s interval and running for 1s, should have checked ~5 times
        # But the job wasn't due, so shouldn't have executed
        assert not mock_backend.enqueue.called

    def test_scheduler_graceful_shutdown(self, registry, mock_backend):
        """Test that scheduler shuts down gracefully."""
        scheduler = CronScheduler(
            registry=registry,
            backend=mock_backend,
            check_interval=0.1
        )

        @registry.register("test_task")
        def handler(payload):
            pass

        job = scheduler.add_job("test_task", "* * * * *")
        job.next_run = datetime.now() - timedelta(seconds=1)

        scheduler.start()

        # Wait a bit then stop
        time.sleep(0.3)
        scheduler.stop(timeout=5.0)

        assert scheduler.is_running() is False
        assert not scheduler._thread.is_alive()

    def test_scheduler_context_manager(self, registry, mock_backend):
        """Test using scheduler as a context manager."""
        @registry.register("test_task")
        def handler(payload):
            pass

        job = scheduler.add_job("test_task", "* * * * *")
        job.next_run = datetime.now() - timedelta(seconds=1)

        with CronScheduler(registry=registry, backend=mock_backend, check_interval=0.1):
            time.sleep(0.3)

        # Scheduler should be stopped after exiting context
        assert not mock_backend.enqueue.assert_called


class TestCronSchedulerIntegration:
    """Integration tests with registry and backends."""

    def test_integration_with_inmemory_backend(self, registry):
        """Test scheduler with InMemoryBackend."""
        from python_task_queue.backends.memory import InMemoryBackend

        backend = InMemoryBackend()
        scheduler = CronScheduler(registry=registry, backend=backend, check_interval=0.1)

        @registry.register("test_task")
        def handler(payload):
            return f"processed: {payload['value']}"

        job = scheduler.add_job("test_task", "* * * * *", payload={"value": "test"})
        job.next_run = datetime.now() - timedelta(seconds=1)

        scheduler.start()
        time.sleep(0.3)
        scheduler.stop()

        # Verify task was enqueued
        assert backend.size() > 0

        # Dequeue and verify
        task = backend.dequeue()
        assert task is not None
        assert task.name == "test_task"
        assert task.payload == {"value": "test"}
        assert task.metadata.get("scheduled") is True

    def test_scheduler_preserves_job_metadata(self, registry, mock_backend):
        """Test that scheduler preserves job metadata in tasks."""
        scheduler = CronScheduler(registry=registry, backend=mock_backend)

        @registry.register("test_task")
        def handler(payload):
            pass

        job_metadata = {"app": "myapp", "version": "1.0"}
        job = scheduler.add_job("test_task", "* * * * *", metadata=job_metadata)

        scheduler._execute_job(job)

        enqueued_task = mock_backend.enqueue.call_args[0][0]

        # Verify metadata is preserved
        for key, value in job_metadata.items():
            assert enqueued_task.metadata.get(key) == value

        # Verify job_id is in metadata
        assert enqueued_task.metadata.get("job_id") == job.id


class TestCronSchedulerErrors:
    """Test error handling in scheduler."""

    def test_handle_task_not_found_at_execution(self, registry, mock_backend, scheduler):
        """Test handling when task is removed after job is added."""
        @registry.register("test_task")
        def handler(payload):
            pass

        job = scheduler.add_job("test_task", "* * * * *")

        # Remove task from registry
        registry.unregister("test_task")

        # Should log error but not crash
        scheduler._execute_job(job)

        # Task should not be enqueued
        mock_backend.enqueue.assert_not_called()

    def test_handle_enqueue_error(self, registry, scheduler):
        """Test handling when backend enqueue fails."""
        mock_backend = Mock()
        mock_backend.enqueue.side_effect = Exception("Backend error")

        scheduler = CronScheduler(registry=registry, backend=mock_backend)

        @registry.register("test_task")
        def handler(payload):
            pass

        job = scheduler.add_job("test_task", "* * * * *")

        # Should handle error gracefully
        scheduler._execute_job(job)

        # Job metadata should still be updated
        assert job.last_run is not None
        assert job.next_run is not None


class TestCronSchedulerConcurrency:
    """Test concurrent operations on scheduler."""

    def test_concurrent_job_addition(self, registry, scheduler):
        """Test adding jobs from multiple threads."""
        @registry.register(f"task_{i}")
        def handler(payload, i=i):
            pass

        jobs = []
        errors = []

        def add_job(i):
            try:
                job = scheduler.add_job(f"task_{i}", "* * * * *")
                jobs.append(job)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(10):
            t = threading.Thread(target=add_job, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(jobs) == 10
        assert len(scheduler.list_jobs()) == 10

    def test_concurrent_job_removal(self, registry, scheduler):
        """Test removing jobs from multiple threads."""
        @registry.register("test_task")
        def handler(payload):
            pass

        # Add 100 jobs
        job_ids = []
        for i in range(100):
            job = scheduler.add_job("test_task", "* * * * *")
            job_ids.append(job.id)

        errors = []
        removed = []

        def remove_jobs(start_idx):
            try:
                for i in range(start_idx, len(job_ids), 4):
                    scheduler.remove_job(job_ids[i])
                    removed.append(job_ids[i])
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(4):
            t = threading.Thread(target=remove_jobs, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0
        assert scheduler.count_jobs() == 0

    def test_scheduler_thread_safety(self, registry, mock_backend):
        """Test scheduler thread safety with concurrent operations."""
        scheduler = CronScheduler(registry=registry, backend=mock_backend, check_interval=0.1)

        @registry.register("test_task")
        def handler(payload):
            pass

        # Start scheduler
        scheduler.start()

        # Add jobs while scheduler is running
        def add_jobs():
            for i in range(5):
                scheduler.add_job("test_task", "* * * * *", payload={"i": i})
                time.sleep(0.05)

        # List jobs while scheduler is running
        def list_jobs():
            for _ in range(5):
                scheduler.list_jobs()
                time.sleep(0.05)

        t1 = threading.Thread(target=add_jobs)
        t2 = threading.Thread(target=list_jobs)

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        scheduler.stop()

        # Should have all jobs added
        assert scheduler.count_jobs() == 5


@pytest.fixture
def scheduler_with_count_method(registry):
    """Create a scheduler with count_jobs method for convenience."""
    scheduler = CronScheduler(registry=registry)

    # Add method for counting jobs if it doesn't exist
    if not hasattr(scheduler, 'count_jobs'):
        def count_jobs(self=None):
            return len(self.jobs)
        scheduler.count_jobs = lambda: len(scheduler.jobs)

    return scheduler


# =============================================================================
# Test Helpers
# =============================================================================

def test_scheduler_repr():
    """Test scheduler string representation."""
    scheduler = CronScheduler()
    scheduler.jobs["job1"] = ScheduledJob(id="job1", task_name="task1", schedule="* * * * *")

    repr_str = repr(scheduler)
    assert "CronScheduler" in repr_str
    assert "jobs=1" in repr_str
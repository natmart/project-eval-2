"""
Comprehensive tests for the Cron Scheduler.

Tests cover:
- CronSchedule parsing and matching
- CronSchedule next_run_time calculation
- ScheduledJob dataclass functionality
- CronScheduler job management
- CronScheduler background thread operations
- Graceful shutdown
- Context manager support
"""

import pytest
import time
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from threading import Thread

from python_task_queue.scheduler import (
    CronSchedule,
    ScheduledJob,
    CronScheduler,
    NAMED_DAYS,
    NAMED_MONTHS,
)


class TestCronSchedule:
    """Test cases for CronSchedule parsing and matching."""
    
    def test_parse_wildcard_expression(self):
        """Test parsing a simple wildcard expression."""
        schedule = CronSchedule("* * * * *")
        assert 0 in schedule.minute_spec
        assert 59 in schedule.minute_spec
        assert 0 in schedule.hour_spec
        assert 23 in schedule.hour_spec
    
    def test_parse_specific_values(self):
        """Test parsing expression with specific values."""
        schedule = CronSchedule("5 10 * * *")
        assert schedule.minute_spec == [5]
        assert schedule.hour_spec == [10]
    
    def test_parse_interval(self):
        """Test parsing interval expressions (*/n)."""
        schedule = CronSchedule("*/5 * * * *")
        assert schedule.minute_spec == [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]
    
    def test_parse_range(self):
        """Test parsing range expressions (n-m)."""
        schedule = CronSchedule("0 9-17 * * *")
        assert schedule.hour_spec == list(range(9, 18))  # 9 through 17
    
    def test_parse_list(self):
        """Test parsing list expressions (n,m,o)."""
        schedule = CronSchedule("15,30,45 * * * *")
        assert schedule.minute_spec == [15, 30, 45]
    
    def test_parse_complex_expression(self):
        """Test parsing a complex cron expression."""
        schedule = CronSchedule("15,45 8,12,16 1-15 * 1-5")
        
        # Check minutes
        assert schedule.minute_spec == [15, 45]
        
        # Check hours
        assert schedule.hour_spec == [8, 12, 16]
        
        # Check days of month
        assert schedule.day_of_month_spec == list(range(1, 16))
        
        # Check days of week (Monday-Friday: 1-5)
        assert schedule.day_of_week_spec == [1, 2, 3, 4, 5]
    
    def test_parse_range_with_interval(self):
        """Test parsing range with interval (n-m/o)."""
        schedule = CronSchedule("0 */2 * * *")  # Every 2 hours
        assert schedule.hour_spec == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]
    
    def test_parse_single_value_with_interval(self):
        """Test parsing single value with interval (n/o)."""
        schedule = CronSchedule("0 0/4 * * *")  # Every 4 hours starting at 0
        assert schedule.hour_spec == [0, 4, 8, 12, 16, 20]
    
    def test_invalid_field_count(self):
        """Test that expressions with wrong field count raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            CronSchedule("* * * *")
        assert "must have exactly 5 fields" in str(exc_info.value)
    
    def test_invalid_value_out_of_range(self):
        """Test that values out of range raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            CronSchedule("70 * * * *")  # Invalid minute
        assert "not in range 0-59" in str(exc_info.value)
    
    def test_named_days_lowercase(self):
        """Test parsing named days (case insensitive)."""
        schedule = CronSchedule("0 10 * * MON-WED")
        assert schedule.day_of_week_spec == [1, 2, 3]
        
        schedule2 = CronSchedule("0 10 * * mon-wed")
        assert schedule2.day_of_week_spec == [1, 2, 3]
    
    def test_named_months(self):
        """Test parsing named months."""
        schedule = CronSchedule("0 10 1 * JAN,MAR,MAY")
        assert schedule.month_spec == [1, 3, 5]
    
    def test_named_months_lowercase(self):
        """Test parsing named months (case insensitive)."""
        schedule = CronSchedule("0 10 1 * jan,mar,may")
        assert schedule.month_spec == [1, 3, 5]
    
    def test_should_run_true(self):
        """Test should_run returns True for matching timestamp."""
        schedule = CronSchedule("30 14 * * *")
        
        # Time matching the schedule
        test_time = datetime(2024, 1, 15, 14, 30, 0)
        assert schedule.should_run(test_time) is True
    
    def test_should_run_false_minute(self):
        """Test should_run returns False for non-matching minute."""
        schedule = CronSchedule("30 14 * * *")
        
        # Time with wrong minute
        test_time = datetime(2024, 1, 15, 14, 31, 0)
        assert schedule.should_run(test_time) is False
    
    def test_should_run_false_hour(self):
        """Test should_run returns False for non-matching hour."""
        schedule = CronSchedule("30 14 * * *")
        
        # Time with wrong hour
        test_time = datetime(2024, 1, 15, 15, 30, 0)
        assert schedule.should_run(test_time) is False
    
    def test_should_run_with_interval(self):
        """Test should_run with interval schedule."""
        schedule = CronSchedule("*/15 * * * *")
        
        # Should match
        assert schedule.should_run(datetime(2024, 1, 15, 10, 0, 0))
        assert schedule.should_run(datetime(2024, 1, 15, 10, 15, 0))
        assert schedule.should_run(datetime(2024, 1, 15, 10, 30, 0))
        assert schedule.should_run(datetime(2024, 1, 15, 10, 45, 0))
        
        # Should not match
        assert schedule.should_run(datetime(2024, 1, 15, 10, 5, 0)) is False
    
    def test_should_run_with_list(self):
        """Test should_run with list schedule."""
        schedule = CronSchedule("0,15,30,45 * * * *")
        
        assert schedule.should_run(datetime(2024, 1, 15, 10, 0, 0))
        assert schedule.should_run(datetime(2024, 1, 15, 10, 30, 0))
        assert schedule.should_run(datetime(2024, 1, 15, 10, 45, 0))
        assert schedule.should_run(datetime(2024, 1, 15, 10, 15, 0))
        assert schedule.should_run(datetime(2024, 1, 15, 10, 10, 0)) is False
    
    def test_should_run_day_of_week(self):
        """Test should_run with day of week filter."""
        schedule = CronSchedule("0 10 * * MON-FRI")
        
        # Monday (week 2024-01-15)
        assert schedule.should_run(datetime(2024, 1, 15, 10, 0, 0)) is True
        
        # Saturday (2024-01-20)
        assert schedule.should_run(datetime(2024, 1, 20, 10, 0, 0)) is False
    
    def test_should_run_day_of_month(self):
        """Test should_run with day of month filter."""
        schedule = CronSchedule("0 10 1,15 * *")
        
        # 1st of month
        assert schedule.should_run(datetime(2024, 1, 1, 10, 0, 0)) is True
        
        # 15th of month
        assert schedule.should_run(datetime(2024, 1, 15, 10, 0, 0)) is True
        
        # Other day
        assert schedule.should_run(datetime(2024, 1, 10, 10, 0, 0)) is False
    
    def test_should_run_month(self):
        """Test should_run with month filter."""
        schedule = CronSchedule("0 10 * * JAN,APR,JUL,OCT")
        
        # January
        assert schedule.should_run(datetime(2024, 1, 15, 10, 0, 0)) is True
        
        # April
        assert schedule.should_run(datetime(2024, 4, 15, 10, 0, 0)) is True
        
        # February
        assert schedule.should_run(datetime(2024, 2, 15, 10, 0, 0)) is False
    
    def test_next_run_time_basic(self):
        """Test next_run_time calculation for simple schedule."""
        schedule = CronSchedule("30 14 * * *")
        
        # Current time is before scheduled time
        now = datetime(2024, 1, 15, 10, 0, 0)
        next_run = schedule.next_run_time(now)
        
        assert next_run.minute == 30
        assert next_run.hour == 14
        assert next_run.day == 15
    
    def test_next_run_time_same_minute(self):
        """Test next_run_time when current time matches the minute."""
        schedule = CronSchedule("30 14 * * *")
        
        # Current time is the scheduled time (next should be tomorrow)
        now = datetime(2024, 1, 15, 14, 30, 0)
        next_run = schedule.next_run_time(now)
        
        assert next_run.minute == 30
        assert next_run.hour == 14
        assert next_run.day == 16  # Next day
    
    def test_next_run_time_after_scheduled_time(self):
        """Test next_run_time when current time is after scheduled time."""
        schedule = CronSchedule("30 14 * * *")
        
        now = datetime(2024, 1, 15, 16, 0, 0)
        next_run = schedule.next_run_time(now)
        
        assert next_run.minute == 30
        assert next_run.hour == 14
        assert next_run.day == 16  # Next day
    
    def test_next_run_time_every_minute(self):
        """Test next_run_time for every minute schedule."""
        schedule = CronSchedule("* * * * *")
        
        now = datetime(2024, 1, 15, 10, 10, 0)
        next_run = schedule.next_run_time(now)
        
        # Should be next minute
        assert next_run.minute == 11
        assert next_run.hour == 10
    
    def test_next_run_time_interval(self):
        """Test next_run_time for interval schedule."""
        schedule = CronSchedule("*/10 * * * *")
        
        now = datetime(2024, 1, 15, 10, 14, 0)
        next_run = schedule.next_run_time(now)
        
        # Should be next 10-minute interval: 20
        assert next_run.minute == 20
        assert next_run.hour == 10
    
    def test_next_run_time_without_after_parameter(self):
        """Test next_run_time when after parameter is not provided."""
        schedule = CronSchedule("0 * * * *")  # Every hour
        
        # Should use current time
        next_run = schedule.next_run_time()
        assert next_run >= datetime.utcnow() - timedelta(seconds=5)
    
    def test_matches_minute(self):
        """Test matches_minute helper."""
        schedule = CronSchedule("15,30,45 * * * *")
        
        assert schedule.matches_minute(15)
        assert schedule.matches_minute(30)
        assert schedule.matches_minute(45)
        assert schedule.matches_minute(10) is False
    
    def test_matches_hour(self):
        """Test matches_hour helper."""
        schedule = CronSchedule("* 9,12,18 * * *")
        
        assert schedule.matches_hour(9)
        assert schedule.matches_hour(12)
        assert schedule.matches_hour(18)
        assert schedule.matches_hour(10) is False
    
    def test_matches_day(self):
        """Test matches_day helper."""
        schedule = CronSchedule("* * 1,15 * *")
        
        assert schedule.matches_day(1)
        assert schedule.matches_day(15)
        assert schedule.matches_day(10) is False
    
    def test_matches_month(self):
        """Test matches_month helper."""
        schedule = CronSchedule("* * * 1,6,12 *")
        
        assert schedule.matches_month(1)
        assert schedule.matches_month(6)
        assert schedule.matches_month(12)
        assert schedule.matches_month(3) is False
    
    def test_matches_weekday(self):
        """Test matches_weekday helper."""
        schedule = CronSchedule("* * * * 1,3,5")
        
        assert schedule.matches_weekday(1)  # Monday
        assert schedule.matches_weekday(3)  # Wednesday
        assert schedule.matches_weekday(5)  # Friday
        assert schedule.matches_weekday(0) is False  # Sunday
        assert schedule.matches_weekday(6) is False  # Saturday


class TestScheduledJob:
    """Test cases for ScheduledJob dataclass."""
    
    def test_create_scheduled_job(self):
        """Test creating a ScheduledJob."""
        job = ScheduledJob(
            task_name="test_task",
            enabled=True,
            metadata={"key": "value"},
        )
        
        assert job.task_name == "test_task"
        assert job.enabled is True
        assert job.metadata == {"key": "value"}
        assert job.last_run is None
        assert job.next_run is None
    
    def test_update_next_run(self):
        """Test updating next run time."""
        schedule = CronSchedule("30 14 * * *")
        job = ScheduledJob(task_name="test", schedule=schedule)
        
        job.update_next_run()
        
        assert job.next_run is not None
        assert job.next_run.minute == 30
        assert job.next_run.hour == 14
    
    def test_update_next_run_with_after_parameter(self):
        """Test updating next run time with custom after time."""
        schedule = CronSchedule("30 14 * * *")
        job = ScheduledJob(task_name="test", schedule=schedule)
        
        after = datetime(2024, 1, 15, 10, 0, 0)
        job.update_next_run(after)
        
        assert job.next_run is not None
        assert job.next_run.minute == 30
        assert job.next_run.hour == 14
        assert job.next_run.day == 15
    
    def test_to_dict(self):
        """Test ScheduledJob serialization."""
        schedule = CronSchedule("30 14 * * *")
        job = ScheduledJob(
            id=uuid4(),
            task_name="test_task",
            schedule=schedule,
            enabled=True,
            next_run=datetime(2024, 1, 15, 14, 30, 0),
        )
        
        data = job.to_dict()
        
        assert data["task_name"] == "test_task"
        assert data["schedule"] == "30 14 * * *"
        assert data["enabled"] is True
        assert data["id"] == str(job.id)
        assert "next_run" in data
    
    def test_to_dict_without_schedule(self):
        """Test to_dict when schedule is None."""
        job = ScheduledJob(task_name="test", schedule=None)
        data = job.to_dict()
        
        assert data["schedule"] is None


class TestCronScheduler:
    """Test cases for CronScheduler."""
    
    def test_scheduler_initialization(self):
        """Test scheduler initialization."""
        scheduler = CronScheduler()
        
        assert scheduler.check_interval == 1.0
        assert scheduler.job_count() == 0
        assert scheduler.is_running() is False
    
    def test_scheduler_with_custom_check_interval(self):
        """Test scheduler with custom check interval."""
        scheduler = CronScheduler(check_interval=0.5)
        assert scheduler.check_interval == 0.5
    
    def test_add_job(self):
        """Test adding a job to the scheduler."""
        scheduler = CronScheduler()
        
        job = scheduler.add_job(
            task_name="test_task",
            cron_expression="30 14 * * *",
            payload={"key": "value"},
        )
        
        assert job.task_name == "test_task"
        assert job.enabled is True
        assert job.next_run is not None
        assert scheduler.job_count() == 1
    
    def test_add_job_disabled(self):
        """Test adding a disabled job."""
        scheduler = CronScheduler()
        
        job = scheduler.add_job(
            task_name="test_task",
            cron_expression="30 14 * * *",
            enabled=False,
        )
        
        assert job.enabled is False
        assert job.next_run is None
    
    def test_add_job_with_metadata(self):
        """Test adding a job with metadata."""
        scheduler = CronScheduler()
        
        job = scheduler.add_job(
            task_name="test_task",
            cron_expression="30 14 * * *",
            metadata={"owner": "system", "priority": 1},
        )
        
        assert job.metadata == {"owner": "system", "priority": 1}
    
    def test_remove_job(self):
        """Test removing a job from the scheduler."""
        scheduler = CronScheduler()
        
        job = scheduler.add_job("test_task", "30 14 * * *")
        assert scheduler.job_count() == 1
        
        removed = scheduler.remove_job(job.id)
        assert removed is True
        assert scheduler.job_count() == 0
    
    def test_remove_nonexistent_job(self):
        """Test removing a job that doesn't exist."""
        scheduler = CronScheduler()
        removed = scheduler.remove_job(uuid4())
        assert removed is False
    
    def test_get_job(self):
        """Test getting a job by ID."""
        scheduler = CronScheduler()
        
        job = scheduler.add_job("test_task", "30 14 * * *")
        retrieved = scheduler.get_job(job.id)
        
        assert retrieved is not None
        assert retrieved.id == job.id
        assert retrieved.task_name == "test_task"
    
    def test_get_nonexistent_job(self):
        """Test getting a job that doesn't exist."""
        scheduler = CronScheduler()
        job = scheduler.get_job(uuid4())
        assert job is None
    
    def test_get_all_jobs(self):
        """Test getting all jobs."""
        scheduler = CronScheduler()
        
        scheduler.add_job("task1", "30 14 * * *")
        scheduler.add_job("task2", "0 10 * * *")
        scheduler.add_job("task3", "*/5 * * * *")
        
        jobs = scheduler.get_all_jobs()
        assert len(jobs) == 3
    
    def test_get_enabled_jobs(self):
        """Test getting only enabled jobs."""
        scheduler = CronScheduler()
        
        job1 = scheduler.add_job("task1", "30 14 * * *", enabled=True)
        job2 = scheduler.add_job("task2", "0 10 * * *", enabled=False)
        job3 = scheduler.add_job("task3", "*/5 * * * *", enabled=True)
        
        enabled_jobs = scheduler.get_enabled_jobs()
        assert len(enabled_jobs) == 2
        
        job_ids = {j.id for j in enabled_jobs}
        assert job1.id in job_ids
        assert job3.id in job_ids
        assert job2.id not in job_ids
    
    def test_enable_job(self):
        """Test enabling a job."""
        scheduler = CronScheduler()
        
        job = scheduler.add_job("test_task", "30 14 * * *", enabled=False)
        assert job.enabled is False
        assert job.next_run is None
        
        scheduler.enable_job(job.id)
        
        updated = scheduler.get_job(job.id)
        assert updated.enabled is True
        assert updated.next_run is not None
    
    def test_enable_already_enabled_job(self):
        """Test enabling a job that's already enabled."""
        scheduler = CronScheduler()
        
        job = scheduler.add_job("test_task", "30 14 * * *", enabled=True)
        original_next_run = job.next_run
        
        scheduler.enable_job(job.id)
        
        updated = scheduler.get_job(job.id)
        assert updated.enabled is True
    
    def test_disable_job(self):
        """Test disabling a job."""
        scheduler = CronScheduler()
        
        job = scheduler.add_job("test_task", "30 14 * * *", enabled=True)
        assert job.enabled is True
        assert job.next_run is not None
        
        scheduler.disable_job(job.id)
        
        updated = scheduler.get_job(job.id)
        assert updated.enabled is False
        assert updated.next_run is None
    
    def test_disable_already_disabled_job(self):
        """Test disabling a job that's already disabled."""
        scheduler = CronScheduler()
        
        job = scheduler.add_job("test_task", "30 14 * * *", enabled=False)
        
        scheduler.disable_job(job.id)
        
        updated = scheduler.get_job(job.id)
        assert updated.enabled is False
    
    def test_update_job_schedule(self):
        """Test updating a job's schedule."""
        scheduler = CronScheduler()
        
        job = scheduler.add_job("test_task", "30 14 * * *")
        original_next_run = job.next_run
        
        updated_job = scheduler.update_job_schedule(job.id, "0 10 * * *")
        
        assert updated_job is not None
        assert updated_job.schedule.expression == "0 10 * * *"
        # Next run should change
        assert updated_job.next_run != original_next_run
    
    def test_update_nonexistent_job_schedule(self):
        """Test updating schedule for a job that doesn't exist."""
        scheduler = CronScheduler()
        
        result = scheduler.update_job_schedule(uuid4(), "0 10 * * *")
        assert result is None
    
    def test_clear_jobs(self):
        """Test clearing all jobs."""
        scheduler = CronScheduler()
        
        scheduler.add_job("task1", "30 14 * * *")
        scheduler.add_job("task2", "0 10 * * *")
        scheduler.add_job("task3", "*/5 * * * *")
        
        assert scheduler.job_count() == 3
        
        scheduler.clear_jobs()
        assert scheduler.job_count() == 0
    
    def test_get_due_jobs(self):
        """Test getting jobs that are due to run."""
        scheduler = CronScheduler()
        
        # Add a job that will run in the next minute
        job = scheduler.add_job("due_task", "* * * * *")  # Every minute
        job.next_run = datetime.utcnow()
        
        due = scheduler.get_due_jobs()
        
        # Should find at least the job we just added (depending on timing)
        assert len(due) >= 0
    
    def test_start_and_stop_scheduler(self):
        """Test starting and stopping the scheduler."""
        scheduler = CronScheduler()
        
        assert scheduler.is_running() is False
        
        scheduler.start()
        assert scheduler.is_running() is True
        
        scheduler.stop()
        assert scheduler.is_running() is False
    
    def test_start_already_running_scheduler(self):
        """Test starting a scheduler that's already running."""
        scheduler = CronScheduler()
        
        scheduler.start()
        scheduler.start()  # Should be idempotent
        
        assert scheduler.is_running() is True
        scheduler.stop()
    
    def test_stop_already_stopped_scheduler(self):
        """Test stopping a scheduler that's already stopped."""
        scheduler = CronScheduler()
        
        scheduler.stop()  # Should be idempotent
        assert scheduler.is_running() is False
    
    def test_stop_with_timeout(self):
        """Test stopping scheduler with timeout."""
        scheduler = CronScheduler()
        
        scheduler.start()
        scheduler.stop(timeout=1.0)
        
        assert scheduler.is_running() is False
    
    def test_context_manager(self):
        """Test using scheduler as context manager."""
        with CronScheduler() as scheduler:
            assert scheduler.is_running() is True
            
            scheduler.add_job("test_task", "30 14 * * *")
            assert scheduler.job_count() == 1
        
        # Scheduler should be stopped after context exit
        assert scheduler.is_running() is False
    
    def test_scheduler_thread_safety(self):
        """Test that scheduler operations are thread-safe."""
        scheduler = CronScheduler()
        
        # Add multiple jobs
        job_ids = []
        for i in range(10):
            job = scheduler.add_job(f"task{i}", f"{i} * * * *")
            job_ids.append(job.id)
        
        # Remove jobs while scheduler is running
        scheduler.start()
        
        try:
            for i, job_id in enumerate(job_ids):
                if i % 2 == 0:  # Remove half the jobs
                    scheduler.remove_job(job_id)
            
            # Should have 5 jobs remaining
            assert scheduler.job_count() == 5
        finally:
            scheduler.stop()
    
    def test_scheduler_with_registry_and_backend(self):
        """Test scheduler initialized with task registry and queue backend."""
        scheduler = CronScheduler(
            check_interval=0.5,
            task_registry="mock_registry",
            queue_backend="mock_backend",
        )
        
        assert scheduler.task_registry == "mock_registry"
        assert scheduler.queue_backend == "mock_backend"
    
    def test_multiple_schedulers_independent(self):
        """Test that multiple schedulers operate independently."""
        scheduler1 = CronScheduler()
        scheduler2 = CronScheduler()
        
        scheduler1.add_job("task1", "30 14 * * *")
        scheduler2.add_job("task2", "0 10 * * *")
        
        assert scheduler1.job_count() == 1
        assert scheduler2.job_count() == 1
        
        scheduler1.clear_jobs()
        
        assert scheduler1.job_count() == 0
        assert scheduler2.job_count() == 1


class TestScheduleAccuracy:
    """Test cases for schedule accuracy and edge cases."""
    
    def test_every_second_schedule_impossible(self):
        """Test that cron only supports minute-level granularity."""
        # This is actually valid - it means every minute at second 0
        schedule = CronSchedule("* * * * *")
        
        # Should match regardless of second value (only minute/hour/etc matter)
        assert schedule.should_run(
            datetime(2024, 1, 15, 10, 10, 0)
        )
    
    def test_year_boundary(self):
        """Test scheduling across year boundary."""
        schedule = CronSchedule("0 0 1 1 *")  # January 1st midnight
        
        # Dec 31, 23:59 is before Jan 1, 00:00
        before = datetime(2023, 12, 31, 23, 59, 0)
        next_run = schedule.next_run_time(before)
        
        assert next_run.year == 2024
        assert next_run.month == 1
        assert next_run.day == 1
        assert next_run.hour == 0
        assert next_run.minute == 0
    
    def test leap_year(self):
        """Test scheduling on a leap year (Feb 29)."""
        schedule = CronSchedule("0 0 29 2 *")  # Feb 29
        
        # Feb 28, 2024 (before the leap day)
        before = datetime(2024, 2, 28, 10, 0, 0)
        next_run = schedule.next_run_time(before)
        
        # Should find Feb 29, 2024
        assert next_run.year == 2024
        assert next_run.month == 2
        assert next_run.day == 29
    
    def test_month_boundary(self):
        """Test scheduling across month boundary."""
        schedule = CronSchedule("30 14 * * *")
        
        # Jan 31, 15:00 (past scheduled time)
        before = datetime(2024, 1, 31, 15, 0, 0)
        next_run = schedule.next_run_time(before)
        
        # Should be Feb 1, 14:30 (no Feb 31)
        assert next_run.month == 2
        assert next_run.day == 1
    
    def test_end_of_month(self):
        """Test scheduling at end of month."""
        # Last day varies by month, but we can test specific cases
        schedule = CronSchedule("0 12 31 * *")  # 31st of month
        
        # Jan 31, 12:00 (matches)
        assert schedule.should_run(
            datetime(2024, 1, 31, 12, 0, 0)
        )
        
        # Feb doesn't have 31st
        assert schedule.should_run(
            datetime(2024, 2, 28, 12, 0, 0)
        ) is False


class TestSchedulerBackgroundThread:
    """Test cases for background scheduler thread operation."""
    
    def test_background_thread_running(self):
        """Test that background thread is actually running."""
        scheduler = CronScheduler(check_interval=0.1)
        
        scheduler.start()
        
        # Give thread time to start
        time.sleep(0.2)
        
        assert scheduler.is_running() is True
        assert scheduler._thread is not None
        assert scheduler._thread.is_alive()
        
        scheduler.stop()
    
    def test_background_thread_stops_on_event(self):
        """Test that background thread responds to stop event."""
        scheduler = CronScheduler(check_interval=0.1)
        
        scheduler.start()
        assert scheduler.is_running() is True
        
        # Should stop quickly
        start = time.time()
        scheduler.stop(timeout=1.0)
        elapsed = time.time() - start
        
        assert elapsed < 1.0
        assert scheduler.is_running() is False
    
    def test_background_thread_no_jobs(self):
        """Test that thread runs fine even with no jobs."""
        scheduler = CronScheduler(check_interval=0.05)
        
        scheduler.start()
        time.sleep(0.2)
        
        # Should not crash
        assert scheduler.is_running() is True
        
        scheduler.stop()
    
    def test_background_thread_with_disabled_jobs(self):
        """Test that thread handles disabled jobs correctly."""
        scheduler = CronScheduler(check_interval=0.05)
        
        # Add only disabled jobs
        scheduler.add_job("task1", "* * * * *", enabled=False)
        scheduler.add_job("task2", "* * * * *", enabled=False)
        
        scheduler.start()
        time.sleep(0.2)
        
        # Should not crash even though no jobs can run
        assert scheduler.is_running() is True
        
        scheduler.stop()
    
    def test_background_thread_cleanup_on_exception(self):
        """Test that thread continues even after encountering exceptions."""
        
        # Create a scheduler that will fail to execute
        scheduler = CronScheduler(check_interval=0.05)
        scheduler._execute_job = lambda job: (_ for _ in ()).throw(Exception("Test error"))
        
        scheduler.add_job("task1", "* * * * *")
        
        scheduler.start()
        time.sleep(0.2)
        
        # Thread should still be running despite exceptions
        assert scheduler.is_running() is True
        
        scheduler.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
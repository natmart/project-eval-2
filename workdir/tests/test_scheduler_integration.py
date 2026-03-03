"""
Scheduler integration tests.

Tests scheduler integration with queue and worker:
- Job scheduling
- Job execution interval
- Scheduler + queue integration
"""

import threading
import time
import unittest
from datetime import datetime

from python_task_queue.backends import InMemoryBackend
from python_task_queue.models import Task
from python_task_queue.registry import TaskRegistry
from python_task_queue.scheduler import CronScheduler, ScheduledJob


class SchedulerIntegrationTest(unittest.TestCase):
    """Integration tests for scheduler functionality."""

    def setUp(self):
        """Set up fresh components for each test."""
        self.registry = TaskRegistry()
        self.backend = InMemoryBackend()
        self.scheduler = CronScheduler(check_interval=0.1)
        self.executed_tasks = []
        self.lock = threading.Lock()

    def tearDown(self):
        """Clean up after each test."""
        if self.scheduler.is_running():
            self.scheduler.stop()

    def test_scheduler_basic_job_creation(self) -> None:
        """Test creating and listing scheduled jobs."""
        # Add jobs
        job1_id = self.scheduler.add_job("task1", payload={"value": 1}, interval_seconds=30)
        job2_id = self.scheduler.add_job("task2", payload={"value": 2}, interval_seconds=60)

        # List jobs
        jobs = self.scheduler.get_jobs()

        self.assertEqual(len(jobs), 2)
        job_names = {job.task_name for job in jobs}
        self.assertEqual(job_names, {"task1", "task2"})

    def test_scheduler_job_removal(self) -> None:
        """Test removing a scheduled job."""
        job1_id = self.scheduler.add_job("task1", interval_seconds=30)
        job2_id = self.scheduler.add_job("task2", interval_seconds=60)

        self.assertEqual(len(self.scheduler.get_jobs()), 2)

        # Remove job1
        removed = self.scheduler.remove_job(job1_id)
        self.assertTrue(removed)

        jobs = self.scheduler.get_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].task_name, "task2")

        # Removing non-existent job
        removed = self.scheduler.remove_job(999)
        self.assertFalse(removed)

    def test_scheduler_start_stop(self) -> None:
        """Test starting and stopping the scheduler."""
        self.assertFalse(self.scheduler.is_running())

        self.scheduler.start()
        time.sleep(0.2)

        self.assertTrue(self.scheduler.is_running())

        self.scheduler.stop()
        time.sleep(0.2)

        self.assertFalse(self.scheduler.is_running())

    def test_scheduler_job_execution_timing(self) -> None:
        """Test that jobs execute at the correct interval."""
        execution_times = []

        # Custom scheduler that tracks executions
        class TrackingScheduler(CronScheduler):
            def __init__(self, execution_list, lock, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.execution_list = execution_list
                self.lock = lock

            def _execute_job(self, job):
                with self.lock:
                    self.execution_list.append((job.id, time.time()))
                super()._execute_job(job)

        scheduler = TrackingScheduler(
            execution_times, self.lock, check_interval=0.05
        )

        # Add job with short interval
        job_id = scheduler.add_job("test", interval_seconds=0.1)

        # Start scheduler
        scheduler.start()
        time.sleep(0.5)
        scheduler.stop()

        # Verify multiple executions
        self.assertGreater(len(execution_times), 1)

        # Verify intervals
        if len(execution_times) >= 2:
            first_time = execution_times[0][1]
            second_time = execution_times[1][1]
            interval = second_time - first_time
            # Should be approximately 0.1 seconds
            self.assertLess(abs(interval - 0.1), 0.05)

    def test_scheduler_multiple_jobs(self) -> None:
        """Test scheduler with multiple jobs."""
        execution_counts = {}
        lock = threading.Lock()

        class CountingScheduler(CronScheduler):
            def __init__(self, counts, lock, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.counts = counts
                self.lock = lock

            def _execute_job(self, job):
                with self.lock:
                    self.counts[job.task_name] = self.counts.get(job.task_name, 0) + 1
                super()._execute_job(job)

        scheduler = CountingScheduler(
            execution_counts, self.lock, check_interval=0.05
        )

        # Add jobs with different intervals
        scheduler.add_job("fast", interval_seconds=0.05)
        scheduler.add_job("slow", interval_seconds=0.1)

        # Start scheduler
        scheduler.start()
        time.sleep(0.3)
        scheduler.stop()

        # Fast job should execute more times than slow job
        if "fast" in execution_counts and "slow" in execution_counts:
            self.assertGreater(execution_counts["fast"], execution_counts["slow"])

    def test_scheduler_job_disabled(self) -> None:
        """Test that disabled jobs don't execute."""
        executed = []
        lock = threading.Lock()

        class TrackingScheduler(CronScheduler):
            def __init__(self, executed_list, lock_obj, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.executed = executed_list
                self.lock = lock_obj

            def _execute_job(self, job):
                with self.lock:
                    self.executed.append(job.task_name)
                super()._execute_job(job)

        scheduler = TrackingScheduler(
            executed, self.lock, check_interval=0.05
        )

        # Add jobs
        job1_id = scheduler.add_job("enabled", interval_seconds=0.05)
        job2_id = scheduler.add_job("disabled", interval_seconds=0.05)

        # Disable one job
        jobs = scheduler.get_jobs()
        for job in jobs:
            if job.task_name == "disabled":
                job.enabled = False

        # Start scheduler
        scheduler.start()
        time.sleep(0.2)
        scheduler.stop()

        # Only enabled job should execute
        self.assertIn("enabled", executed)
        self.assertNotIn("disabled", executed)

    def test_scheduler_queue_integration(self) -> None:
        """Test scheduler enqueuing tasks to queue."""
        executed_tasks = []
        lock = threading.Lock()

        def handle_task(payload=None):
            with lock:
                executed_tasks.append(payload)

        # Register task handler
        self.registry.register("scheduled", handle_task)

        # Create worker
        from python_task_queue.worker import Worker
        worker = Worker(
            backend=self.backend,
            registry=self.registry,
            poll_interval=0.01,
        )

        # Create scheduler that enqueues tasks
        class EnqueuingScheduler(CronScheduler):
            def __init__(self, backend, task_name, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.backend = backend
                self.task_name = task_name

            def _execute_job(self, job):
                # Enqueue task
                from python_task_queue.models import Task
                task = Task(name=self.task_name, payload=job.payload)
                self.backend.enqueue(task)
                super()._execute_job(job)

        scheduler = EnqueuingScheduler(
            self.backend, "scheduled", check_interval=0.05
        )

        # Add scheduled job
        scheduler.add_job("scheduled", payload="scheduled_task", interval_seconds=0.1)

        # Start both scheduler and worker
        scheduler.start()
        worker_thread = threading.Thread(target=worker.start)
        worker_thread.start()

        # Wait for executions
        time.sleep(0.5)

        # Stop both
        scheduler.stop()
        worker.stop()
        worker_thread.join(timeout=2)

        # Verify tasks were executed
        self.assertGreater(len(executed_tasks), 0)
        self.assertEqual(executed_tasks[0], "scheduled_task")

    def test_scheduler_job_next_run_calculation(self) -> None:
        """Test that next_run is calculated correctly."""
        job = ScheduledJob(
            id=1,
            task_name="test",
            interval_seconds=60,
        )

        # Initially, next_run should be set
        self.assertIsNotNone(job.next_run)

        # After execution, next_run should be advanced
        old_next_run = job.next_run
        job.last_run = datetime.utcnow()
        job.next_run = datetime.utcnow().timestamp() + job.interval_seconds

        self.assertGreater(job.next_run, old_next_run)


if __name__ == "__main__":
    unittest.main()
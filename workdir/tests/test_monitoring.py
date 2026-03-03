"""
Tests for the monitoring system.

Tests cover:
- Monitoring class
- WorkerMetric data class
- QueueMetric data class
- Worker registration/unregistration
- Metric updates
- Summary calculations
"""

import unittest
from datetime import datetime, timedelta
from typing import Any, Dict

from python_task_queue.monitoring import (
    Monitoring,
    WorkerMetric,
    QueueMetric,
)


class TestWorkerMetric(unittest.TestCase):
    """Tests for WorkerMetric data class."""

    def test_worker_metric_creation(self) -> None:
        """Test creating WorkerMetric."""
        metric = WorkerMetric(
            worker_id="worker-1",
            tasks_processed=10,
            tasks_succeeded=8,
            tasks_failed=2,
            tasks_retried=1,
            total_execution_time=5.5,
            start_time=datetime.utcnow(),
            last_activity=datetime.utcnow(),
        )

        self.assertEqual(metric.worker_id, "worker-1")
        self.assertEqual(metric.tasks_processed, 10)
        self.assertEqual(metric.tasks_succeeded, 8)
        self.assertEqual(metric.tasks_failed, 2)
        self.assertEqual(metric.tasks_retried, 1)
        self.assertEqual(metric.total_execution_time, 5.5)

    def test_worker_metric_defaults(self) -> None:
        """Test WorkerMetric default values."""
        metric = WorkerMetric(worker_id="worker-1")

        self.assertEqual(metric.worker_id, "worker-1")
        self.assertEqual(metric.tasks_processed, 0)
        self.assertEqual(metric.tasks_succeeded, 0)
        self.assertEqual(metric.tasks_failed, 0)
        self.assertEqual(metric.tasks_retried, 0)
        self.assertEqual(metric.total_execution_time, 0.0)
        self.assertIsNone(metric.start_time)
        self.assertIsNone(metric.last_activity)


class TestQueueMetric(unittest.TestCase):
    """Tests for QueueMetric data class."""

    def test_queue_metric_creation(self) -> None:
        """Test creating QueueMetric."""
        metric = QueueMetric(
            queue_size=50,
            tasks_pending=20,
            tasks_completed=25,
            tasks_failed=5,
        )

        self.assertEqual(metric.queue_size, 50)
        self.assertEqual(metric.tasks_pending, 20)
        self.assertEqual(metric.tasks_completed, 25)
        self.assertEqual(metric.tasks_failed, 5)

    def test_queue_metric_defaults(self) -> None:
        """Test QueueMetric default values."""
        metric = QueueMetric()

        self.assertEqual(metric.queue_size, 0)
        self.assertEqual(metric.tasks_pending, 0)
        self.assertEqual(metric.tasks_completed, 0)
        self.assertEqual(metric.tasks_failed, 0)


class TestMonitoring(unittest.TestCase):
    """Tests for Monitoring class."""

    def setUp(self):
        """Create a fresh Monitoring instance for each test."""
        self.monitoring = Monitoring()

    def test_monitoring_initialization(self) -> None:
        """Test monitoring system initialization."""
        self.assertEqual(len(self.monitoring._worker_metrics), 0)
        self.assertEqual(len(self.monitoring._queue_metrics), 0)

    def test_register_worker(self) -> None:
        """Test registering a worker."""
        self.monitoring.register_worker("worker-1")

        self.assertIn("worker-1", self.monitoring._worker_metrics)
        metric = self.monitoring._worker_metrics["worker-1"]
        self.assertEqual(metric.worker_id, "worker-1")
        self.assertIsNotNone(metric.start_time)

    def test_register_multiple_workers(self) -> None:
        """Test registering multiple workers."""
        self.monitoring.register_worker("worker-1")
        self.monitoring.register_worker("worker-2")
        self.monitoring.register_worker("worker-3")

        self.assertEqual(len(self.monitoring._worker_metrics), 3)
        self.assertIn("worker-1", self.monitoring._worker_metrics)
        self.assertIn("worker-2", self.monitoring._worker_metrics)
        self.assertIn("worker-3", self.monitoring._worker_metrics)

    def test_unregister_worker(self) -> None:
        """Test unregistering a worker."""
        self.monitoring.register_worker("worker-1")
        self.monitoring.unregister_worker("worker-1")

        self.assertNotIn("worker-1", self.monitoring._worker_metrics)

    def test_unregister_nonexistent_worker(self) -> None:
        """Test unregistering a non-existent worker (should not raise)."""
        # Should not raise an exception
        self.monitoring.unregister_worker("nonexistent")

    def test_unregister_nonexistent_worker_in_dict(self) -> None:
        """Test unregistering when worker exists but not in metrics."""
        # Register a worker
        self.monitoring.register_worker("worker-1")
        # Manually remove from metrics to simulate edge case
        del self.monitoring._worker_metrics["worker-1"]
        # Should not raise
        self.monitoring.unregister_worker("worker-1")


class TestMetricUpdates(unittest.TestCase):
    """Tests for metric update operations."""

    def setUp(self):
        """Create Monitoring instance and register worker."""
        self.monitoring = Monitoring()
        self.monitoring.register_worker("worker-1")

    def test_update_worker_metric_tasks_processed(self) -> None:
        """Test updating tasks processed count."""
        self.monitoring.update_worker_metrics(
            "worker-1",
            tasks_processed=10,
        )

        metric = self.monitoring.get_worker_metrics("worker-1")
        self.assertEqual(metric.tasks_processed, 10)

    def test_update_worker_metric_tasks_succeeded(self) -> None:
        """Test updating tasks succeeded count."""
        self.monitoring.update_worker_metrics(
            "worker-1",
            tasks_succeeded=8,
        )

        metric = self.monitoring.get_worker_metrics("worker-1")
        self.assertEqual(metric.tasks_succeeded, 8)

    def test_update_worker_metric_tasks_failed(self) -> None:
        """Test updating tasks failed count."""
        self.monitoring.update_worker_metrics(
            "worker-1",
            tasks_failed=2,
        )

        metric = self.monitoring.get_worker_metrics("worker-1")
        self.assertEqual(metric.tasks_failed, 2)

    def test_update_worker_metric_tasks_retried(self) -> None:
        """Test updating tasks retried count."""
        self.monitoring.update_worker_metrics(
            "worker-1",
            tasks_retried=1,
        )

        metric = self.monitoring.get_worker_metrics("worker-1")
        self.assertEqual(metric.tasks_retried, 1)

    def test_update_worker_metric_execution_time(self) -> None:
        """Test updating total execution time."""
        self.monitoring.update_worker_metrics(
            "worker-1",
            total_execution_time=5.5,
        )

        metric = self.monitoring.get_worker_metrics("worker-1")
        self.assertEqual(metric.total_execution_time, 5.5)

    def test_update_multiple_metrics(self) -> None:
        """Test updating multiple metrics at once."""
        self.monitoring.update_worker_metrics(
            "worker-1",
            tasks_processed=10,
            tasks_succeeded=8,
            tasks_failed=2,
            tasks_retried=1,
            total_execution_time=5.5,
        )

        metric = self.monitoring.get_worker_metrics("worker-1")
        self.assertEqual(metric.tasks_processed, 10)
        self.assertEqual(metric.tasks_succeeded, 8)
        self.assertEqual(metric.tasks_failed, 2)
        self.assertEqual(metric.tasks_retried, 1)
        self.assertEqual(metric.total_execution_time, 5.5)

    def test_update_updates_last_activity(self) -> None:
        """Test updating metrics sets last_activity timestamp."""
        before = datetime.utcnow()
        import time
        time.sleep(0.01)  # Small delay

        self.monitoring.update_worker_metrics(
            "worker-1",
            tasks_processed=5,
        )

        metric = self.monitoring.get_worker_metrics("worker-1")
        self.assertIsNotNone(metric.last_activity)
        # Should be after the time we recorded before
        self.assertGreater(metric.last_activity, before)

    def test_update_none_parameters_dont_change_values(self) -> None:
        """Test that None parameters don't overwrite existing values."""
        # Set initial values
        self.monitoring.update_worker_metrics(
            "worker-1",
            tasks_processed=10,
            tasks_succeeded=8,
        )

        # Update with partial updates (None for other fields)
        self.monitoring.update_worker_metrics(
            "worker-1",
            tasks_processed=20,
        )

        metric = self.monitoring.get_worker_metrics("worker-1")
        self.assertEqual(metric.tasks_processed, 20)
        self.assertEqual(metric.tasks_succeeded, 8)  # Should still be 8


class TestMetricRetrieval(unittest.TestCase):
    """Tests for metric retrieval operations."""

    def setUp(self):
        """Create Monitoring instance and register workers."""
        self.monitoring = Monitoring()
        self.monitoring.register_worker("worker-1")
        self.monitoring.register_worker("worker-2")

    def test_get_worker_metrics(self) -> None:
        """Test getting metrics for a specific worker."""
        self.monitoring.update_worker_metrics(
            "worker-1",
            tasks_processed=10,
        )

        metric = self.monitoring.get_worker_metrics("worker-1")

        self.assertIsNotNone(metric)
        self.assertEqual(metric.worker_id, "worker-1")
        self.assertEqual(metric.tasks_processed, 10)

    def test_get_worker_metrics_none_for_nonexistent(self) -> None:
        """Test getting metrics for non-existent worker returns None."""
        metric = self.monitoring.get_worker_metrics("nonexistent")
        self.assertIsNone(metric)

    def test_get_all_workers(self) -> None:
        """Test getting metrics for all workers."""
        self.monitoring.update_worker_metrics("worker-1", tasks_processed=5)
        self.monitoring.update_worker_metrics("worker-2", tasks_processed=10)

        all_metrics = self.monitoring.get_all_workers()

        self.assertEqual(len(all_metrics), 2)
        worker_ids = {m.worker_id for m in all_metrics}
        self.assertEqual(worker_ids, {"worker-1", "worker-2"})


class TestMonitoringSummary(unittest.TestCase):
    """Tests for monitoring summary calculations."""

    def setUp(self):
        """Create Monitoring with registered workers."""
        self.monitoring = Monitoring()
        self.monitoring.register_worker("worker-1")
        self.monitoring.register_worker("worker-2")
        self.monitoring.register_worker("worker-3")

    def test_summary_empty_metrics(self) -> None:
        """Test summary with no metrics."""
        empty_monitoring = Monitoring()
        summary = empty_monitoring.get_summary()

        self.assertEqual(summary["workers"], 0)
        self.assertEqual(summary["total_tasks_processed"], 0)
        self.assertEqual(summary["total_tasks_succeeded"], 0)
        self.assertEqual(summary["total_tasks_failed"], 0)
        self.assertEqual(summary["total_tasks_retried"], 0)

    def test_summary_aggregates_workers(self) -> None:
        """Test summary aggregates across all workers."""
        self.monitoring.update_worker_metrics("worker-1", tasks_processed=10, tasks_succeeded=8, tasks_failed=2, tasks_retried=0)
        self.monitoring.update_worker_metrics("worker-2", tasks_processed=15, tasks_succeeded=12, tasks_failed=3, tasks_retried=1)
        self.monitoring.update_worker_metrics("worker-3", tasks_processed=5, tasks_succeeded=5, tasks_failed=0, tasks_retried=0)

        summary = self.monitoring.get_summary()

        self.assertEqual(summary["workers"], 3)
        self.assertEqual(summary["total_tasks_processed"], 30)
        self.assertEqual(summary["total_tasks_succeeded"], 25)
        self.assertEqual(summary["total_tasks_failed"], 5)
        self.assertEqual(summary["total_tasks_retried"], 1)

    def test_summary_with_zero_values(self) -> None:
        """Test summary with workers that have zero tasks."""
        self.monitoring.register_worker("worker-4")  # No tasks updated

        summary = self.monitoring.get_summary()

        self.assertEqual(summary["workers"], 4)
        self.assertEqual(summary["total_tasks_processed"], 0)

    def test_summary_updates_dynamically(self) -> None:
        """Test summary reflects updates dynamically."""
        summary1 = self.monitoring.get_summary()
        self.assertEqual(summary1["total_tasks_processed"], 0)

        self.monitoring.update_worker_metrics("worker-1", tasks_processed=10)

        summary2 = self.monitoring.get_summary()
        self.assertEqual(summary2["total_tasks_processed"], 10)


class TestAutoRegistration(unittest.TestCase):
    """Tests for automatic worker registration."""

    def test_update_metrics_registers_worker(self) -> None:
        """Test updating metrics auto-registers worker."""
        monitoring = Monitoring()

        # Don't explicitly register, just update
        monitoring.update_worker_metrics(
            "auto-worker",
            tasks_processed=5,
        )

        # Worker should be auto-registered
        metric = monitoring.get_worker_metrics("auto-worker")
        self.assertIsNotNone(metric)
        self.assertEqual(metric.worker_id, "auto-worker")
        self.assertEqual(metric.tasks_processed, 5)


class TestMetricScenarios(unittest.TestCase):
    """Real-world metric scenario tests."""

    def test_worker_complete_workflow(self) -> None:
        """Test a worker's complete metrics workflow."""
        monitoring = Monitoring()

        # Register worker when it starts
        monitoring.register_worker("worker-1")

        # Worker processes a task successfully
        monitoring.update_worker_metrics("worker-1", tasks_processed=1, tasks_succeeded=1, total_execution_time=0.5)

        # Worker processes another task that fails
        monitoring.update_worker_metrics("worker-1", tasks_processed=2, tasks_succeeded=1, tasks_failed=1, tasks_retried=0, total_execution_time=1.0)

        # Worker processes a task that's retried
        monitoring.update_worker_metrics("worker-1", tasks_processed=3, tasks_succeeded=1, tasks_failed=1, tasks_retried=1, total_execution_time=2.5)

        # Get final metrics
        metric = monitoring.get_worker_metrics("worker-1")

        self.assertEqual(metric.tasks_processed, 3)
        self.assertEqual(metric.tasks_succeeded, 1)
        self.assertEqual(metric.tasks_failed, 1)
        self.assertEqual(metric.tasks_retried, 1)
        self.assertEqual(metric.total_execution_time, 2.5)
        self.assertIsNotNone(metric.start_time)
        self.assertIsNotNone(metric.last_activity)

    def test_multiple_workers_summary(self) -> None:
        """Test summary across multiple workers with different loads."""
        monitoring = Monitoring()

        # Light worker
        monitoring.register_worker("light-worker")
        monitoring.update_worker_metrics("light-worker", tasks_processed=5, tasks_succeeded=5, tasks_failed=0)

        # Medium worker
        monitoring.register_worker("medium-worker")
        monitoring.update_worker_metrics("medium-worker", tasks_processed=50, tasks_succeeded=45, tasks_failed=5)

        # Heavy worker
        monitoring.register_worker("heavy-worker")
        monitoring.update_worker_metrics("heavy-worker", tasks_processed=500, tasks_succeeded=450, tasks_failed=50)

        summary = monitoring.get_summary()

        self.assertEqual(summary["workers"], 3)
        self.assertEqual(summary["total_tasks_processed"], 555)
        self.assertEqual(summary["total_tasks_succeeded"], 500)
        self.assertEqual(summary["total_tasks_failed"], 55)


if __name__ == "__main__":
    unittest.main()
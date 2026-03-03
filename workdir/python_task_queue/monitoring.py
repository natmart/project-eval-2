"""
Monitoring module for the Python Task Queue Library.

Provides basic monitoring and statistics functionality.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


@dataclass
class WorkerMetric:
    """Metrics for a worker instance."""
    worker_id: str
    tasks_processed: int = 0
    tasks_succeeded: int = 0
    tasks_failed: int = 0
    tasks_retried: int = 0
    total_execution_time: float = 0.0
    start_time: Optional[datetime] = None
    last_activity: Optional[datetime] = None


@dataclass
class QueueMetric:
    """Metrics for a queue backend."""
    queue_size: int = 0
    tasks_pending: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0


class Monitoring:
    """
    Monitoring system for task queue operations.

    Collects and reports metrics from workers and queues.
    """

    def __init__(self):
        """Initialize the monitoring system."""
        self._worker_metrics: Dict[str, WorkerMetric] = {}
        self._queue_metrics: Dict[str, QueueMetric] = {}

    def register_worker(self, worker_id: str) -> None:
        """
        Register a worker for monitoring.

        Args:
            worker_id: Unique worker identifier
        """
        self._worker_metrics[worker_id] = WorkerMetric(
            worker_id=worker_id,
            start_time=datetime.utcnow(),
        )
        logger.info(f"Registered worker {worker_id} for monitoring")

    def unregister_worker(self, worker_id: str) -> None:
        """
        Unregister a worker.

        Args:
            worker_id: Worker identifier
        """
        if worker_id in self._worker_metrics:
            del self._worker_metrics[worker_id]
            logger.info(f"Unregistered worker {worker_id}")

    def update_worker_metrics(
        self,
        worker_id: str,
        tasks_processed: Optional[int] = None,
        tasks_succeeded: Optional[int] = None,
        tasks_failed: Optional[int] = None,
        tasks_retried: Optional[int] = None,
        total_execution_time: Optional[float] = None,
    ) -> None:
        """
        Update metrics for a worker.

        Args:
            worker_id: Worker identifier
            tasks_processed: Optional count of processed tasks
            tasks_succeeded: Optional count of succeeded tasks
            tasks_failed: Optional count of failed tasks
            tasks_retried: Optional count of retried tasks
            total_execution_time: Optional total execution time
        """
        if worker_id not in self._worker_metrics:
            self.register_worker(worker_id)

        metric = self._worker_metrics[worker_id]

        if tasks_processed is not None:
            metric.tasks_processed = tasks_processed
        if tasks_succeeded is not None:
            metric.tasks_succeeded = tasks_succeeded
        if tasks_failed is not None:
            metric.tasks_failed = tasks_failed
        if tasks_retried is not None:
            metric.tasks_retried = tasks_retried
        if total_execution_time is not None:
            metric.total_execution_time = total_execution_time

        metric.last_activity = datetime.utcnow()

    def get_worker_metrics(self, worker_id: str) -> Optional[WorkerMetric]:
        """
        Get metrics for a specific worker.

        Args:
            worker_id: Worker identifier

        Returns:
            WorkerMetric or None if not found
        """
        return self._worker_metrics.get(worker_id)

    def get_all_workers(self) -> List[WorkerMetric]:
        """Get metrics for all workers."""
        return list(self._worker_metrics.values())

    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all monitored metrics.

        Returns:
            Dictionary with aggregated statistics
        """
        if not self._worker_metrics:
            return {
                "workers": 0,
                "total_tasks_processed": 0,
                "total_tasks_succeeded": 0,
                "total_tasks_failed": 0,
                "total_tasks_retried": 0,
            }

        total_processed = sum(m.tasks_processed for m in self._worker_metrics.values())
        total_succeeded = sum(m.tasks_succeeded for m in self._worker_metrics.values())
        total_failed = sum(m.tasks_failed for m in self._worker_metrics.values())
        total_retried = sum(m.tasks_retried for m in self._worker_metrics.values())

        return {
            "workers": len(self._worker_metrics),
            "total_tasks_processed": total_processed,
            "total_tasks_succeeded": total_succeeded,
            "total_tasks_failed": total_failed,
            "total_tasks_retried": total_retried,
        }
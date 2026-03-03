"""
SQLite persistent backend implementation for the Python Task Queue Library.

This module provides a SQLite-based backend with full task persistence,
atomic operations, connection pooling, and transaction safety.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from uuid import UUID

from python_task_queue.backends.base import QueueBackend, QueueBackendError, TaskNotFoundError
from python_task_queue.models import Task, TaskStatus, TaskResult

logger = logging.getLogger(__name__)


class ConnectionPool:
    """
    Simple thread-safe connection pool for SQLite connections.

    Attributes:
        database_path: Path to the SQLite database file
        max_connections: Maximum number of connections in the pool
        timeout: Timeout in seconds for getting a connection
    """

    def __init__(
        self,
        database_path: str,
        max_connections: int = 5,
        timeout: float = 30.0,
    ):
        """
        Initialize the connection pool.

        Args:
            database_path: Path to the SQLite database file
            max_connections: Maximum number of connections in the pool
            timeout: Timeout in seconds for getting a connection
        """
        self.database_path = database_path
        self.max_connections = max_connections
        self.timeout = timeout
        self._pool: List[sqlite3.Connection] = []
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(max_connections)

    def get_connection(self) -> sqlite3.Connection:
        """
        Get a connection from the pool, creating one if necessary.

        Returns:
            A SQLite connection

        Raises:
            QueueBackendError: If connection cannot be obtained
        """
        if not self._semaphore.acquire(timeout=self.timeout):
            raise QueueBackendError(
                f"Timeout waiting for connection after {self.timeout}s"
            )

        with self._lock:
            try:
                if self._pool:
                    conn = self._pool.pop()
                else:
                    conn = self._create_connection()
                return conn
            except Exception as e:
                self._semaphore.release()
                raise QueueBackendError(f"Failed to get connection: {e}") from e

    def return_connection(self, conn: sqlite3.Connection) -> None:
        """
        Return a connection to the pool.

        Args:
            conn: The connection to return
        """
        with self._lock:
            if conn not in self._pool:
                if len(self._pool) < self.max_connections:
                    self._pool.append(conn)
                else:
                    conn.close()
            self._semaphore.release()

    def _create_connection(self) -> sqlite3.Connection:
        """
        Create a new SQLite connection with proper settings.

        Returns:
            A new SQLite connection
        """
        # Ensure parent directory exists
        db_path = Path(self.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(
            self.database_path,
            check_same_thread=False,
            isolation_level=None,  # Autocommit mode, we manage transactions manually
        )

        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")

        # Set busy timeout for handling concurrent access
        conn.execute("PRAGMA busy_timeout=5000")

        # Optimize for better performance
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-10000")  # 10MB cache
        conn.execute("PRAGMA temp_store=MEMORY")

        return conn

    def close_all(self) -> None:
        """Close all connections in the pool."""
        with self._lock:
            for conn in self._pool:
                try:
                    conn.close()
                except Exception:
                    pass
            self._pool.clear()

    @contextmanager
    def connection(self):
        """
        Context manager for using a connection from the pool.

        Yields:
            A SQLite connection that will be automatically returned
        """
        conn = self.get_connection()
        try:
            yield conn
        finally:
            self.return_connection(conn)


class SQLiteBackend(QueueBackend):
    """
    SQLite-based persistent queue backend implementation.

    This backend provides full task persistence with atomic operations,
    proper transaction handling, and connection pooling.

    Example:
        >>> backend = SQLiteBackend("tasks.db")
        >>> task = Task(name="process_data", payload={"key": "value"})
        >>> backend.enqueue(task)
        >>> next_task = backend.dequeue()
        >>> if next_task:
        ...     # Process the task
        ...     backend.acknowledge(next_task.id)
    """

    def __init__(
        self,
        database_path: str = "taskqueue.db",
        pool_size: int = 5,
        auto_create: bool = True,
    ):
        """
        Initialize the SQLite backend.

        Args:
            database_path: Path to the SQLite database file
            pool_size: Maximum number of connections in the pool
            auto_create: Whether to auto-create tables on initialization
        """
        self.database_path = database_path
        self.pool = ConnectionPool(database_path, max_connections=pool_size)
        self._local = threading.local()

        if auto_create:
            self._create_tables()

        logger.info(f"SQLiteBackend initialized with database: {database_path}")

    def _create_tables(self) -> None:
        """Create the necessary database tables if they don't exist."""
        with self.pool.connection() as conn:
            cursor = conn.cursor()

            # Main tasks table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    payload TEXT,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    result TEXT,
                    error TEXT,  -- Deprecated, kept for backward compatibility
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 3,
                    metadata TEXT,
                    enqueued_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))
                )
            """)

            # Create indexes for performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status_priority
                ON tasks (status, priority)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_enqueued_at
                ON tasks (enqueued_at)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status
                ON tasks (status)
            """)

            conn.commit()
            logger.debug("Database tables created/verified")

    def _serialize_task(self, task: Task) -> dict:
        """
        Convert a Task object to a dictionary for database storage.

        Args:
            task: The task to serialize

        Returns:
            Dictionary with serialized task data
        """
        data = task.to_dict()

        # Convert result to JSON if present
        if task.result:
            data["result"] = task.result.to_dict()

        return data

    def _deserialize_task(self, data: dict) -> Task:
        """
        Convert database data to a Task object.

        Args:
            data: Dictionary from database

        Returns:
            Task object
        """
        # Handle result deserialization
        if data.get("result"):
            data["result"] = TaskResult.from_dict(data["result"])

        return Task.from_dict(data)

    @contextmanager
    def _transaction(self):
        """
        Context manager for handling database transactions.

        Yields:
            A cursor for executing SQL statements
        """
        with self.pool.connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute("BEGIN IMMEDIATE TRANSACTION")
                yield cursor
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def enqueue(self, task: Task) -> None:
        """
        Add a task to the queue.

        Args:
            task: The task to add to the queue

        Raises:
            QueueBackendError: If the task cannot be enqueued
        """
        if not isinstance(task.id, UUID):
            raise ValueError(f"Task ID must be a UUID, got {type(task.id)}")

        data = self._serialize_task(task)

        try:
            with self._transaction() as cursor:
                cursor.execute("""
                    INSERT INTO tasks (
                        id, name, payload, status, priority,
                        created_at, started_at, completed_at,
                        result, error, retry_count, max_retries, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(task.id),
                    task.name,
                    json.dumps(task.payload) if task.payload is not None else None,
                    task.status.value,
                    task.priority,
                    task.created_at.isoformat() if task.created_at else None,
                    task.started_at.isoformat() if task.started_at else None,
                    task.completed_at.isoformat() if task.completed_at else None,
                    json.dumps(data.get("result")) if data.get("result") else None,
                    task.error,  # Deprecated field
                    task.retry_count,
                    task.max_retries,
                    json.dumps(task.metadata) if task.metadata else None,
                ))
            logger.debug(f"Task {task.id} enqueued successfully")
        except sqlite3.IntegrityError as e:
            raise QueueBackendError(f"Task {task.id} already exists") from e
        except Exception as e:
            raise QueueBackendError(f"Failed to enqueue task {task.id}: {e}") from e

    def dequeue(self) -> Optional[Task]:
        """
        Remove and return the next task from the queue.

        This method uses an atomic SELECT+UPDATE pattern to ensure that
        multiple workers don't dequeue the same task.

        Returns:
            The next task to process, or None if the queue is empty
        """
        try:
            with self._transaction() as cursor:
                # First, find the next high-priority pending task
                cursor.execute("""
                    SELECT id, name, payload, status, priority,
                           created_at, started_at, completed_at,
                           result, error, retry_count, max_retries, metadata
                    FROM tasks
                    WHERE status = 'pending'
                    ORDER BY priority ASC, enqueued_at ASC
                    LIMIT 1
                """)

                row = cursor.fetchone()
                if row is None:
                    return None

                # Update the task status to running
                task_id = row[0]
                cursor.execute("""
                    UPDATE tasks
                    SET status = 'running',
                        started_at = ?
                    WHERE id = ?
                """, (datetime.utcnow().isoformat(), task_id))

                # Deserialize task
                task_data = {
                    "id": row[0],
                    "name": row[1],
                    "payload": json.loads(row[2]) if row[2] else None,
                    "status": row[3],
                    "priority": row[4],
                    "created_at": row[5],
                    "started_at": row[6],
                    "completed_at": row[7],
                    "result": json.loads(row[8]) if row[8] else None,
                    "error": row[9],
                    "retry_count": row[10],
                    "max_retries": row[11],
                    "metadata": json.loads(row[12]) if row[12] else None,
                }

                task = self._deserialize_task(task_data)
                logger.debug(f"Task {task.id} dequeued successfully")
                return task

        except Exception as e:
            raise QueueBackendError(f"Failed to dequeue task: {e}") from e

    def peek(self) -> Optional[Task]:
        """
        Return the next task from the queue without removing it.

        Returns:
            The next task that would be returned by dequeue(), or None if the queue is empty
        """
        try:
            with self.pool.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, name, payload, status, priority,
                           created_at, started_at, completed_at,
                           result, error, retry_count, max_retries, metadata
                    FROM tasks
                    WHERE status = 'pending'
                    ORDER BY priority ASC, enqueued_at ASC
                    LIMIT 1
                """)

                row = cursor.fetchone()
                if row is None:
                    return None

                task_data = {
                    "id": row[0],
                    "name": row[1],
                    "payload": json.loads(row[2]) if row[2] else None,
                    "status": row[3],
                    "priority": row[4],
                    "created_at": row[5],
                    "started_at": row[6],
                    "completed_at": row[7],
                    "result": json.loads(row[8]) if row[8] else None,
                    "error": row[9],
                    "retry_count": row[10],
                    "max_retries": row[11],
                    "metadata": json.loads(row[12]) if row[12] else None,
                }

                return self._deserialize_task(task_data)

        except Exception as e:
            raise QueueBackendError(f"Failed to peek at queue: {e}") from e

    def size(self) -> int:
        """
        Return the number of tasks currently in the queue.

        Returns:
            The number of pending tasks in the queue
        """
        try:
            with self.pool.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM tasks
                    WHERE status = 'pending'
                """)
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            raise QueueBackendError(f"Failed to get queue size: {e}") from e

    def acknowledge(self, task_id: UUID) -> None:
        """
        Mark a task as successfully completed.

        Args:
            task_id: The UUID of the task to acknowledge

        Raises:
            TaskNotFoundError: If no task with the given ID exists
            QueueBackendError: If the task cannot be acknowledged
        """
        try:
            with self._transaction() as cursor:
                cursor.execute("""
                    UPDATE tasks
                    SET status = 'completed',
                        completed_at = ?
                    WHERE id = ?
                """, (datetime.utcnow().isoformat(), str(task_id)))

                if cursor.rowcount == 0:
                    raise TaskNotFoundError(task_id)

                logger.debug(f"Task {task_id} acknowledged successfully")

        except TaskNotFoundError:
            raise
        except Exception as e:
            raise QueueBackendError(
                f"Failed to acknowledge task {task_id}: {e}"
            ) from e

    def fail(self, task_id: UUID, error: str) -> None:
        """
        Mark a task as failed and record the error.

        Args:
            task_id: The UUID of the task to mark as failed
            error: A description of the error that caused the failure

        Raises:
            TaskNotFoundError: If no task with the given ID exists
            QueueBackendError: If the task cannot be failed
        """
        try:
            with self._transaction() as cursor:
                # First, get the current task state to check retry status
                cursor.execute("""
                    SELECT retry_count, max_retries, result
                    FROM tasks
                    WHERE id = ?
                """, (str(task_id),))

                row = cursor.fetchone()
                if row is None:
                    raise TaskNotFoundError(task_id)

                retry_count, max_retries, result_json = row

                # Determine if task should be retried
                can_retry = retry_count < max_retries
                new_status = "retrying" if can_retry else "failed"
                new_retry_count = retry_count + 1

                # Update result with error information
                result = {
                    "success": False,
                    "error": error,
                    "metadata": {},
                }
                if result_json:
                    existing_result = json.loads(result_json)
                    result.update(existing_result)

                cursor.execute("""
                    UPDATE tasks
                    SET status = ?,
                        completed_at = ?,
                        retry_count = ?,
                        result = ?,
                        error = ?
                    WHERE id = ?
                """, (
                    new_status,
                    datetime.utcnow().isoformat(),
                    new_retry_count,
                    json.dumps(result),
                    error,  # Deprecated field
                    str(task_id),
                ))

                logger.debug(
                    f"Task {task_id} marked as {new_status} "
                    f"(retry {new_retry_count}/{max_retries})"
                )

        except TaskNotFoundError:
            raise
        except Exception as e:
            raise QueueBackendError(f"Failed to mark task {task_id} as failed: {e}") from e

    def get_task(self, task_id: UUID) -> Optional[Task]:
        """
        Retrieve a task by its ID.

        Args:
            task_id: The UUID of the task to retrieve

        Returns:
            The task with the given ID, or None if it doesn't exist
        """
        try:
            with self.pool.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, name, payload, status, priority,
                           created_at, started_at, completed_at,
                           result, error, retry_count, max_retries, metadata
                    FROM tasks
                    WHERE id = ?
                """, (str(task_id),))

                row = cursor.fetchone()
                if row is None:
                    return None

                task_data = {
                    "id": row[0],
                    "name": row[1],
                    "payload": json.loads(row[2]) if row[2] else None,
                    "status": row[3],
                    "priority": row[4],
                    "created_at": row[5],
                    "started_at": row[6],
                    "completed_at": row[7],
                    "result": json.loads(row[8]) if row[8] else None,
                    "error": row[9],
                    "retry_count": row[10],
                    "max_retries": row[11],
                    "metadata": json.loads(row[12]) if row[12] else None,
                }

                return self._deserialize_task(task_data)

        except Exception as e:
            raise QueueBackendError(f"Failed to get task {task_id}: {e}") from e

    def list_tasks(
        self, status: Optional[TaskStatus] = None
    ) -> List[Task]:
        """
        List tasks, optionally filtered by status.

        Args:
            status: Optional status filter. If None, return all tasks.

        Returns:
            A list of tasks matching the criteria
        """
        try:
            with self.pool.connection() as conn:
                cursor = conn.cursor()

                if status is None:
                    cursor.execute("""
                        SELECT id, name, payload, status, priority,
                               created_at, started_at, completed_at,
                               result, error, retry_count, max_retries, metadata
                        FROM tasks
                        ORDER BY priority ASC, enqueued_at DESC
                    """)
                else:
                    cursor.execute("""
                        SELECT id, name, payload, status, priority,
                               created_at, started_at, completed_at,
                               result, error, retry_count, max_retries, metadata
                        FROM tasks
                        WHERE status = ?
                        ORDER BY priority ASC, enqueued_at DESC
                    """, (status.value,))

                tasks = []
                for row in cursor.fetchall():
                    task_data = {
                        "id": row[0],
                        "name": row[1],
                        "payload": json.loads(row[2]) if row[2] else None,
                        "status": row[3],
                        "priority": row[4],
                        "created_at": row[5],
                        "started_at": row[6],
                        "completed_at": row[7],
                        "result": json.loads(row[8]) if row[8] else None,
                        "error": row[9],
                        "retry_count": row[10],
                        "max_retries": row[11],
                        "metadata": json.loads(row[12]) if row[12] else None,
                    }
                    tasks.append(self._deserialize_task(task_data))

                return tasks

        except Exception as e:
            raise QueueBackendError(f"Failed to list tasks: {e}") from e

    def clear(self) -> None:
        """
        Remove all tasks from the queue.

        This is a destructive operation that cannot be undone.
        """
        try:
            with self._transaction() as cursor:
                cursor.execute("DELETE FROM tasks")
            logger.debug("All tasks cleared from queue")
        except Exception as e:
            raise QueueBackendError(f"Failed to clear queue: {e}") from e

    def close(self) -> None:
        """
        Close the backend and release all resources.

        After calling this method, the backend cannot be used anymore.
        """
        self.pool.close_all()
        logger.info("SQLiteBackend closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
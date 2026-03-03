"""
SQLite backend implementation for the Python Task Queue Library.

Provides persistent task storage using SQLite database.
"""

import logging
import sqlite3
import threading
from dataclasses import asdict
from datetime import datetime
from typing import Any, List, Optional

from python_task_queue.backends.base import QueueBackend
from python_task_queue.models import Task


logger = logging.getLogger(__name__)


class SQLiteBackend(QueueBackend):
    """
    SQLite-based queue backend for persistent task storage.

    This backend stores tasks in a SQLite database, providing persistence
    across process restarts. Tasks are stored in JSON-serialized format.

    Attributes:
        db_path: Path to the SQLite database file
        lock: Thread lock for concurrent access
    """

    def __init__(self, db_path: str = ":memory:"):
        """
        Initialize SQLite backend.

        Args:
            db_path: Path to SQLite database file. Use ":memory:" for in-memory database.
        """
        self.db_path = db_path
        self.lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

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
                    error TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    metadata TEXT,
                    queued_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_priority ON tasks (priority ASC, queued_at ASC)
            """)

            conn.commit()
            conn.close()

    def _task_to_dict(self, task: Task) -> dict:
        """Convert task to dictionary for storage."""
        import json

        result_data = None
        if task.result:
            result_data = json.dumps(asdict(task.result))

        metadata_data = None
        if task.metadata:
            metadata_data = json.dumps(task.metadata)

        payload_data = None
        if task.payload:
            payload_data = json.dumps(task.payload)

        return {
            "id": str(task.id),
            "name": task.name,
            "payload": payload_data,
            "status": task.status.value,
            "priority": task.priority,
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "result": result_data,
            "error": task.error,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "metadata": metadata_data,
        }

    def _dict_to_task(self, data: dict) -> Task:
        """Convert dictionary from storage to Task."""
        import json
        from uuid import UUID
        from python_task_queue.models import TaskStatus, TaskResult

        payload = None
        if data.get("payload"):
            payload = json.loads(data["payload"])

        result = None
        if data.get("result"):
            result_dict = json.loads(data["result"])
            result = TaskResult(**result_dict)

        metadata = {}
        if data.get("metadata"):
            metadata = json.loads(data["metadata"])

        task_data = {
            "id": UUID(data["id"]),
            "name": data["name"],
            "payload": payload,
            "status": TaskStatus.from_string(data["status"]),
            "priority": data["priority"],
            "created_at": datetime.fromisoformat(data["created_at"]),
            "started_at": datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            "completed_at": datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            "result": result,
            "error": data.get("error"),
            "retry_count": data["retry_count"],
            "max_retries": data["max_retries"],
            "metadata": metadata,
        }

        return Task(**task_data)

    def enqueue(self, task: Task) -> None:
        """Add a task to the queue."""
        with self.lock:
            import json

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            data = self._task_to_dict(task)

            payload_data = None
            if task.payload:
                payload_data = json.dumps(task.payload)

            cursor.execute("""
                INSERT INTO tasks (
                    id, name, payload, status, priority, created_at,
                    started_at, completed_at, result, error, retry_count,
                    max_retries, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["id"],
                data["name"],
                payload_data,
                data["status"],
                data["priority"],
                data["created_at"],
                data["started_at"],
                data["completed_at"],
                data["result"],
                data["error"],
                data["retry_count"],
                data["max_retries"],
                data["metadata"],
            ))

            conn.commit()
            conn.close()

    def dequeue(self) -> Optional[Task]:
        """Remove and return the highest priority task from the queue."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Get highest priority task
            cursor.execute("""
                SELECT * FROM tasks
                ORDER BY priority ASC, queued_at ASC
                LIMIT 1
            """)

            row = cursor.fetchone()

            if row is None:
                conn.close()
                return None

            # Get column names
            columns = [description[0] for description in cursor.description]
            data = dict(zip(columns, row))

            # Delete the task
            cursor.execute("DELETE FROM tasks WHERE id = ?", (data["id"],))
            conn.commit()
            conn.close()

            return self._dict_to_task(data)

    def peek(self) -> Optional[Task]:
        """Return the highest priority task without removing it."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM tasks
                ORDER BY priority ASC, queued_at ASC
                LIMIT 1
            """)

            row = cursor.fetchone()

            if row is None:
                conn.close()
                return None

            # Get column names
            columns = [description[0] for description in cursor.description]
            data = dict(zip(columns, row))

            conn.close()
            return self._dict_to_task(data)

    def size(self) -> int:
        """Return the number of tasks in the queue."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM tasks")
            count = cursor.fetchone()[0]

            conn.close()
            return count

    def list(self) -> List[Task]:
        """Return all tasks in the queue ordered by priority."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM tasks
                ORDER BY priority ASC, queued_at ASC
            """)

            tasks = []
            for row in cursor.fetchall():
                columns = [description[0] for description in cursor.description]
                data = dict(zip(columns, row))
                tasks.append(self._dict_to_task(data))

            conn.close()
            return tasks

    def clear(self) -> None:
        """Remove all tasks from the queue."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("DELETE FROM tasks")
            conn.commit()
            conn.close()

    def update_task(self, task_id: str, **updates: Any) -> Optional[Task]:
        """Update a task in the queue."""
        with self.lock:
            import json

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Check if task exists
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()

            if row is None:
                conn.close()
                return None

            # Build update query
            update_fields = []
            update_values = []

            for field, value in updates.items():
                if field == "status":
                    update_fields.append("status = ?")
                    update_values.append(value.value if hasattr(value, "value") else value)
                elif field in ["created_at", "started_at", "completed_at"]:
                    update_fields.append(f"{field} = ?")
                    update_values.append(value.isoformat() if value else None)
                elif field in ["payload", "metadata"]:
                    update_fields.append(f"{field} = ?")
                    update_values.append(json.dumps(value) if value else None)
                elif field == "result":
                    if value:
                        update_fields.append("result = ?")
                        update_values.append(json.dumps(value.__dict__))
                elif field == "error":
                    update_fields.append("error = ?")
                    update_values.append(value)
                else:
                    update_fields.append(f"{field} = ?")
                    update_values.append(value)

            update_values.append(task_id)

            if update_fields:
                cursor.execute(f"""
                    UPDATE tasks SET {', '.join(update_fields)}
                    WHERE id = ?
                """, update_values)
                conn.commit()

            # Get updated task
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()

            columns = [description[0] for description in cursor.description]
            data = dict(zip(columns, row))

            conn.close()
            return self._dict_to_task(data)

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()

            if row is None:
                conn.close()
                return None

            columns = [description[0] for description in cursor.description]
            data = dict(zip(columns, row))

            conn.close()
            return self._dict_to_task(data)

    def delete_task(self, task_id: str) -> bool:
        """Delete a task by ID."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            deleted = cursor.rowcount > 0

            conn.commit()
            conn.close()

            return deleted

    def count_by_status(self, status: Any) -> int:
        """Count tasks by status."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            status_value = status.value if hasattr(status, "value") else status
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = ?", (status_value,))
            count = cursor.fetchone()[0]

            conn.close()
            return count
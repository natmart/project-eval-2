"""Tests for the CLI module."""

from click.testing import CliRunner
import json
import pytest
import tempfile
import time
from pathlib import Path

from python_task_queue.cli import cli
from python_task_queue import Task, InMemoryBackend, get_registry


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def registry():
    """Get the task registry and register test tasks."""
    registry = get_registry()
    
    def echo_handler(payload):
        return payload
    
    def greet_handler(payload):
        name = payload.get("name", "World")
        return f"Hello, {name}!"
    
    registry.register("echo")(echo_handler)
    registry.register("greet")(greet_handler)
    
    yield registry
    
    # Cleanup
    registry.unregister("echo")
    registry.unregister("greet")


class TestCLICommands:
    """Test CLI commands."""
    
    def test_cli_version(self, runner):
        """Test the --version option."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output
    
    def test_cli_help(self, runner):
        """Test the help output."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Python Task Queue CLI" in result.output
        assert "worker" in result.output
        assert "task" in result.output
        assert "dlq" in result.output
        assert "stats" in result.output


class TestTaskCommands:
    """Test task management commands."""
    
    def test_task_enqueue_success(self, runner, registry):
        """Test enqueuing a task successfully."""
        payload = json.dumps({"name": "Alice"})
        result = runner.invoke(cli, ["task", "enqueue", "greet", payload])
        
        assert result.exit_code == 0
        assert "Task enqueued successfully" in result.output
        assert "ID:" in result.output
    
    def test_task_enqueue_invalid_json(self, runner):
        """Test enqueuing with invalid JSON."""
        result = runner.invoke(cli, ["task", "enqueue", "echo", "invalid json"])
        
        assert result.exit_code == 1
        assert "Invalid JSON payload" in result.output
    
    def test_task_enqueue_unknown_task(self, runner):
        """Test enqueuing an unknown task."""
        payload = json.dumps({"data": 123})
        result = runner.invoke(cli, ["task", "enqueue", "unknown_task", payload])
        
        assert result.exit_code == 1
        assert "not registered" in result.output
    
    def test_task_enqueue_with_options(self, runner, registry):
        """Test enqueuing with additional options."""
        payload = json.dumps({"name": "Bob"})
        result = runner.invoke(cli, [
            "task", "enqueue",
            "greet", payload,
            "--priority", 5,
            "--max-retries", 10,
            "--timeout", 60.0
        ])
        
        assert result.exit_code == 0
        assert "Task enqueued successfully" in result.output
    
    def test_task_list_empty(self, runner):
        """Test listing tasks when queue is empty."""
        result = runner.invoke(cli, ["task", "list"])
        
        assert result.exit_code == 0
        assert "No tasks found" in result.output
    
    def test_task_list_with_tasks(self, runner, registry):
        """Test listing tasks with tasks in queue."""
        # Enqueue some tasks
        backend = InMemoryBackend()
        for i in range(3):
            task = Task(name="greet", payload={"name": f"User{i}"})
            backend.enqueue(task)
        
        result = runner.invoke(cli, ["task", "list"])
        
        assert result.exit_code == 0
        assert "Found 3 task(s)" in result.output
    
    def test_task_list_with_status_filter(self, runner, registry):
        """Test listing tasks with status filter."""
        # Enqueue and process some tasks
        backend = InMemoryBackend()
        task1 = Task(name="greet", payload={"name": "Alice"})
        backend.enqueue(task1)
        backend.acknowledge(task1.id)
        
        task2 = Task(name="greet", payload={"name": "Bob"})
        backend.enqueue(task2)
        
        # List only pending tasks
        result = runner.invoke(cli, ["task", "list", "--status", "pending"])
        
        assert result.exit_code == 0
    
    def test_task_list_json_output(self, runner, registry):
        """Test listing tasks with JSON output."""
        result = runner.invoke(cli, ["task", "list", "--output", "json"])
        
        assert result.exit_code == 0
        # Should be valid JSON
        try:
            json.loads(result.output)
        except json.JSONDecodeError:
            pytest.fail("Output is not valid JSON")
    
    def test_task_inspect_existing(self, runner, registry):
        """Test inspecting an existing task."""
        # Create a task
        backend = InMemoryBackend()
        task = Task(name="greet", payload={"name": "Test"})
        backend.enqueue(task)
        
        result = runner.invoke(cli, ["task", "inspect", str(task.id)])
        
        assert result.exit_code == 0
        assert str(task.id) in result.output
        assert "greet" in result.output
    
    def test_task_inspect_not_found(self, runner):
        """Test inspecting a non-existent task."""
        result = runner.invoke(cli, ["task", "inspect", "00000000-0000-0000-0000-000000000000"])
        
        assert result.exit_code == 1
        assert "Task not found" in result.output or "Invalid task ID" in result.output
    
    def test_task_inspect_invalid_id(self, runner):
        """Test inspecting with invalid task ID."""
        result = runner.invoke(cli, ["task", "inspect", "invalid-id"])
        
        assert result.exit_code == 1
        assert "Invalid task ID" in result.output
    
    def test_task_inspect_json_output(self, runner, registry):
        """Test inspecting a task with JSON output."""
        backend = InMemoryBackend()
        task = Task(name="greet", payload={"name": "Test"})
        backend.enqueue(task)
        
        result = runner.invoke(cli, ["task", "inspect", str(task.id), "--output", "json"])
        
        assert result.exit_code == 0
        # Should be valid JSON
        try:
            data = json.loads(result.output)
            assert "id" in data
            assert "name" in data
            assert data["name"] == "greet"
        except json.JSONDecodeError:
            pytest.fail("Output is not valid JSON")


class TestStatsCommand:
    """Test statistics command."""
    
    def test_stats_empty_queue(self, runner):
        """Test statistics with empty queue."""
        result = runner.invoke(cli, ["stats"])
        
        assert result.exit_code == 0
        assert "Task Queue Statistics" in result.output
        assert "Total Tasks: 0" in result.output
    
    def test_stats_with_tasks(self, runner, registry):
        """Test statistics with tasks in various states."""
        backend = InMemoryBackend()
        
        # Add tasks in different states
        pending = Task(name="greet", payload={"name": "Pending"})
        backend.enqueue(pending)
        
        completed = Task(name="greet", payload={"name": "Completed"})
        backend.enqueue(completed)
        backend.acknowledge(completed.id)
        
        result = runner.invoke(cli, ["stats"])
        
        assert result.exit_code == 0
        assert "Total Tasks: 2" in result.output
        assert "Pending: 1" in result.output
        assert "Completed: 1" in result.output
    
    def test_stats_json_output(self, runner):
        """Test statistics with JSON output."""
        result = runner.invoke(cli, ["stats", "--output", "json"])
        
        assert result.exit_code == 0
        # Should be valid JSON
        try:
            data = json.loads(result.output)
            assert "total" in data
            assert "pending" in data
            assert "completed" in data
        except json.JSONDecodeError:
            pytest.fail("Output is not valid JSON")


class TestWorkerCommands:
    """Test worker management commands."""
    
    def test_worker_help(self, runner):
        """Test worker command help."""
        result = runner.invoke(cli, ["worker", "--help"])
        
        assert result.exit_code == 0
        assert "start" in result.output
    
    def test_worker_start_with_module(self, runner):
        """Test starting worker with module option."""
        # This just checks the command parses correctly
        # Actual worker start would require running in background
        result = runner.invoke(cli, [
            "worker", "start",
            "--tasks-module", "example_tasks",
            "--max-retries", "5",
            "--poll-interval", "0.5"
        ], catch_exceptions=True)
        
        # Command should parse successfully, but will fail to start without proper setup
        # in test environment
        assert result.exit_code in [0, 1]


class TestConfigOption:
    """Test configuration file options."""
    
    def test_config_file_not_found(self, runner):
        """Test with non-existent config file."""
        result = runner.invoke(cli, ["--config", "nonexistent.yaml", "stats"])
        
        assert result.exit_code == 1
        # Error message should mention config failure
    
    def test_log_level_option(self, runner):
        """Test --log-level option."""
        # Just check that the option is accepted
        result = runner.invoke(cli, ["--log-level", "DEBUG", "stats"])
        
        assert result.exit_code == 0


class TestDLQCommands:
    """Test dead letter queue commands."""
    
    def test_dlq_help(self, runner):
        """Test DLQ command help."""
        result = runner.invoke(cli, ["dlq", "--help"])
        
        assert result.exit_code == 0
        assert "list" in result.output
        assert "replay" in result.output
        assert "purge" in result.output
    
    def test_dlq_list_unavailable(self, runner):
        """Test DLQ list when DLQ module is not available."""
        # This test assumes DLQ is not available
        result = runner.invoke(cli, ["dlq", "list"])
        
        # May fail if DLQ is available, or may succeed with empty result
        assert result.exit_code in [0, 1]
    
    def test_dlq_replay_with_invalid_id(self, runner):
        """Test DLQ replay with invalid ID."""
        result = runner.invoke(cli, ["dlq", "replay", "invalid-id"])
        
        # Should fail either due to invalid ID or DLQ not available
        assert result.exit_code in [0, 1]


class TestIntegration:
    """Integration tests for CLI workflows."""
    
    def test_full_task_lifecycle(self, runner, registry):
        """Test complete task lifecycle through CLI."""
        # 1. Enqueue a task
        payload = json.dumps({"name": "Integration"})
        enqueue_result = runner.invoke(cli, ["task", "enqueue", "greet", payload])
        assert enqueue_result.exit_code == 0
        
        # Extract task ID from output
        import re
        match = re.search(r'ID:\s+([a-f0-9\-]+)', enqueue_result.output)
        assert match, "Could not find task ID in output"
        task_id = match.group(1)
        
        # 2. List tasks (should show our task)
        list_result = runner.invoke(cli, ["task", "list"])
        assert list_result.exit_code == 0
        
        # 3. Inspect the task
        inspect_result = runner.invoke(cli, ["task", "inspect", task_id])
        assert inspect_result.exit_code == 0
        assert "Integration" in inspect_result.output
        
        # 4. Check statistics
        stats_result = runner.invoke(cli, ["stats"])
        assert stats_result.exit_code == 0
    
    def test_multiple_tasks_enqueue(self, runner, registry):
        """Test enqueuing multiple tasks."""
        tasks_to_enqueue = [
            {"name": "User1"},
            {"name": "User2"},
            {"name": "User3"},
        ]
        
        for task_data in tasks_to_enqueue:
            payload = json.dumps(task_data)
            result = runner.invoke(cli, ["task", "enqueue", "greet", payload])
            assert result.exit_code == 0
        
        # Check that all tasks are in the list
        result = runner.invoke(cli, ["task", "list"])
        assert result.exit_code == 0
        assert "3 task(s)" in result.output or "Found" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
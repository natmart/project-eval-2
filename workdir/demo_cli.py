#!/usr/bin/env python3
"""
Demonstration script for the Task Queue CLI.

This script shows how to use the CLI programmatically for testing and examples.
"""

import json
import sys
import time
from click.testing import CliRunner

# Import the CLI
from python_task_queue.cli import cli
from python_task_queue import get_registry, Task, InMemoryBackend


def register_example_tasks():
    """Register example task handlers for demonstration."""
    registry = get_registry()
    
    def greet_handler(payload):
        name = payload.get("name", "World")
        return f"Hello, {name}!"
    
    def process_data_handler(payload):
        data = payload.get("data", 0)
        return data * 2
    
    def send_email_handler(payload):
        return {
            "status": "sent",
            "to": payload.get("to"),
            "subject": payload.get("subject")
        }
    
    # Register tasks
    registry.register("greet")(greet_handler)
    registry.register("process_data")(process_data_handler)
    registry.register("send_email")(send_email_handler)
    
    print("✓ Example tasks registered")


def demo_cli_basics():
    """Demonstrate basic CLI commands."""
    print("\n" + "="*60)
    print("DEMO 1: Basic CLI Commands")
    print("="*60 + "\n")
    
    runner = CliRunner()
    
    # Test version
    print("1. Testing version command...")
    result = runner.invoke(cli, ["--version"])
    print(f"   Output: {result.output.strip()}")
    assert result.exit_code == 0
    print("   ✓ Version command works\n")
    
    # Test help
    print("2. Testing help command...")
    result = runner.invoke(cli, ["--help"])
    print(f"   Available commands: {', '.join(result.output.split())[:50]}...")
    assert result.exit_code == 0
    print("   ✓ Help command works\n")


def demo_task_operations():
    """Demonstrate task operations through CLI."""
    print("\n" + "="*60)
    print("DEMO 2: Task Operations")
    print("="*60 + "\n")
    
    runner = CliRunner()
    
    # Enqueue tasks
    print("1. Enqueuing tasks...")
    
    tasks = [
        ("greet", {"name": "Alice"}),
        ("greet", {"name": "Bob"}),
        ("process_data", {"data": 21}),
        ("send_email", {"to": "user@example.com", "subject": "Test"}),
    ]
    
    for name, payload in tasks:
        result = runner.invoke(cli, [
            "task", "enqueue", name, json.dumps(payload)
        ])
        print(f"   Enqueued {name}: {result.output.strip()}")
        assert result.exit_code == 0
    
    print("   ✓ All tasks enqueued\n")
    
    # List tasks
    print("2. Listing tasks...")
    result = runner.invoke(cli, ["task", "list"])
    print(f"   {result.output}")
    assert result.exit_code == 0
    print("   ✓ Tasks listed\n"
    
    # Get statistics
    print("3. Getting statistics...")
    result = runner.invoke(cli, ["stats"])
    print(f"   {result.output}")
    assert result.exit_code == 0
    print("   ✓ Statistics retrieved\n"
    
    # Test JSON output
    print("4. Testing JSON output...")
    result = runner.invoke(cli, ["task", "list", "--output", "json"])
    print(f"   JSON output preview: {result.output[:100]}...")
    assert result.exit_code == 0
    print("   ✓ JSON output works\n"


def demo_task_inspection():
    """Demonstrate task inspection."""
    print("\n" + "="*60)
    print("DEMO 3: Task Inspection")
    print("="*60 + "\n")
    
    runner = CliRunner()
    
    # Manually create a task to get its ID
    backend = InMemoryBackend()
    task = Task(name="greet", payload={"name": "Inspection Test"})
    backend.enqueue(task)
    
    print(f"1. Created task: {task.id}")
    
    # Inspect the task
    print(f"2. Inspecting task...")
    result = runner.invoke(cli, ["task", "inspect", str(task.id)])
    print(f"   Output:\n{result.output}")
    assert result.exit_code == 0
    print("   ✓ Task inspection works\n")
    
    # Inspect with JSON output
    print(f"3. Inspecting task (JSON format)...")
    result = runner.invoke(cli, ["task", "inspect", str(task.id), "--output", "json"])
    data = json.loads(result.output)
    print(f"   Task name: {data['name']}")
    print(f"   Task status: {data['status']}")
    print("   ✓ JSON inspection works\n")


def demo_status_filtering():
    """Demonstrate status filtering."""
    print("\n" + "="*60)
    print("DEMO 4: Status Filtering")
    print("="*60 + "\n")
    
    backend = InMemoryBackend()
    
    # Create tasks in different states
    pending = Task(name="greet", payload={"name": "Pending"})
    backend.enqueue(pending)
    
    completed = Task(name="greet", payload={"name": "Completed"})
    backend.enqueue(completed)
    backend.acknowledge(completed.id)
    
    runner = CliRunner()
    
    # List pending tasks
    print("1. Listing pending tasks...")
    result = runner.invoke(cli, ["task", "list", "--status", "pending"])
    print(f"   {result.output}")
    
    # List completed tasks
    print("2. Listing completed tasks...")
    result = runner.invoke(cli, ["task", "list", "--status", "completed"])
    print(f"   {result.output}")
    
    print("   ✓ Status filtering works\n")


def demo_cli_options():
    """Demonstrate CLI options."""
    print("\n" + "="*60)
    print("DEMO 5: CLI Options")
    print("="*60 + "\n")
    
    runner = CliRunner()
    
    # Test with different log levels
    print("1. Testing with DEBUG log level...")
    result = runner.invoke(cli, ["--log-level", "DEBUG", "stats"])
    assert result.exit_code == 0
    print("   ✓ DEBUG level works\n")
    
    # Test with different backends
    print("2. Testing with memory backend...")
    result = runner.invoke(cli, ["--backend", "memory", "stats"])
    assert result.exit_code == 0
    print("   ✓ Memory backend works\n")
    
    print("   ✓ CLI options work correctly\n")


def demo_error_handling():
    """Demonstrate error handling."""
    print("\n" + "="*60)
    print("DEMO 6: Error Handling")
    print("="*60 + "\n")
    
    runner = CliRunner()
    
    # Test with invalid task name
    print("1. Testing invalid task name...")
    result = runner.invoke(cli, [
        "task", "enqueue", "nonexistent_task", '{"data": 123}'
    ])
    assert result.exit_code == 1
    print("   ✓ Invalid task name rejected")
    
    # Test with invalid JSON
    print("2. Testing invalid JSON payload...")
    result = runner.invoke(cli, [
        "task", "enqueue", "greet", "invalid json"
    ])
    assert result.exit_code == 1
    print("   ✓ Invalid JSON rejected")
    
    # Test with invalid task ID
    print("3. Testing invalid task ID...")
    result = runner.invoke(cli, [
        "task", "inspect", "invalid-id"
    ])
    assert result.exit_code == 1
    print("   ✓ Invalid task ID rejected")
    
    print("   ✓ Error handling works correctly\n")


def main():
    """Run all demonstrations."""
    print("\n" + "="*60)
    print("PYTHON TASK QUEUE CLI DEMONSTRATIONS")
    print("="*60)
    
    try:
        # Register example tasks
        register_example_tasks()
        
        # Run demos
        demo_cli_basics()
        demo_task_operations()
        demo_task_inspection()
        demo_status_filtering()
        demo_cli_options()
        demo_error_handling()
        
        print("\n" + "="*60)
        print("ALL DEMONSTRATIONS COMPLETED SUCCESSFULLY")
        print("="*60 + "\n")
        
        return 0
    
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
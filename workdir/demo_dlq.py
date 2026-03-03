#!/usr/bin/env python3
"""
Demo script showcasing the Dead Letter Queue system.

This script demonstrates:
- Creating and managing failed tasks
- Inspecting and filtering DLQ entries
- Replaying failed tasks back to main queue
- Purging operations
- Statistics and monitoring
"""

import time
from datetime import datetime, timedelta

from python_task_queue import (
    DeadLetterQueue,
    DeadLetterTask,
    Task,
    TaskStatus,
    create_dlq,
)


def print_header(title):
    """Print a formatted header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)


def print_subheader(title):
    """Print a formatted subheader."""
    print(f"\n{'-'*70}")
    print(f"  {title}")
    print('-'*70)


def demo_basic_operations():
    """Demo 1: Basic DLQ operations."""
    print_header("Demo 1: Basic DLQ Operations")

    # Initialize DLQ
    dlq = DeadLetterQueue()
    print(f"✅ DLQ initialized: {dlq}")

    # Create a failed task
    task = Task(
        name="failing_api_call",
        payload={"url": "https://api.example.com/data", "retries": 0}
    )
    task.fail(
        error="Connection timeout after 30s",
        error_type="TimeoutError",
    )
    print(f"✅ Task created and failed: {task.name}")
    print(f"   Status: {task.status}, Retry count: {task.retry_count}")

    # Add to DLQ
    dead_letter = dlq.add_failed_task(
        task=task,
        original_queue="main",
        reason="timeout",
        error_message="Service unavailable",
        error_type="TimeoutError",
        retry_count=3,
        metadata={"attempts": 4, "last_attempt": "2024-03-03"},
    )
    print(f"✅ Added to DLQ with ID: {dead_letter.id}")
    print(f"   Reason: {dead_letter.reason}, Queue: {dead_letter.original_queue}")

    # Inspect
    print(f"\n📊 DLQ count: {dlq.count()}")
    tasks = dlq.inspect()
    print(f"📋 Failed tasks: {len(tasks)}")
    for dlq_task in tasks:
        print(f"   - {dlq_task.task.name}: {dlq_task.reason}")


def demo_adding_multiple_tasks():
    """Demo 2: Adding multiple failed tasks with different characteristics."""
    print_header("Demo 2: Adding Multiple Failed Tasks")

    dlq = DeadLetterQueue()

    # Simulating different failure scenarios
    failure_scenarios = [
        {
            "name": "payment_processing",
            "payload": {"amount": 100, "currency": "USD"},
            "error": "Payment gateway timeout",
            "error_type": "TimeoutError",
            "queue": "payments",
            "reason": "timeout",
        },
        {
            "name": "email_notification",
            "payload": {"to": "user@example.com", "template": "welcome"},
            "error": "SMTP server unavailable",
            "error_type": "ConnectionError",
            "queue": "notifications",
            "reason": "service_not_available",
        },
        {
            "name": "data_sync",
            "payload": {"source": "api", "target": "database"},
            "error": "Invalid JSON response",
            "error_type": "ValueError",
            "queue": "sync",
            "reason": "invalid_payload",
        },
        {
            "name": "report_generation",
            "payload": {"type": "monthly", "format": "pdf"},
            "error": "Insufficient disk space",
            "error_type": "OSError",
            "queue": "reports",
            "reason": "permission_denied",
        },
        {
            "name": "cache_refresh",
            "payload": {"keys": ["user:1", "user:2", "user:3"]},
            "error": "Redis connection refused",
            "error_type": "ConnectionError",
            "queue": "cache",
            "reason": "service_not_available",
        },
    ]

    for i, scenario in enumerate(failure_scenarios, 1):
        task = Task(name=scenario["name"], payload=scenario["payload"])
        task.retry_count = i  # Simulate different retry counts
        task.fail(error=scenario["error"], error_type=scenario["error_type"])

        dead_letter = dlq.add_failed_task(
            task=task,
            original_queue=scenario["queue"],
            reason=scenario["reason"],
            error_message=scenario["error"],
            error_type=scenario["error_type"],
            retry_count=task.retry_count,
        )

        print(f"✅ {i}. {scenario['name']:25} → {scenario['reason']:25} [{scenario['queue']}]")
        time.sleep(0.01)  # Small delay for timestamp differences

    print(f"\n📊 Total tasks in DLQ: {dlq.count()}")


def demo_filtering():
    """Demo 3: Filtering DLQ entries."""
    print_header("Demo 3: Filtering DLQ Entries")

    # Add some tasks (reusing function from previous demo)
    dlq = DeadLetterQueue()

    tasks_data = [
        ("task1", "main", "timeout"),
        ("task2", "main", "max_retries_exceeded"),
        ("task3", "priority", "timeout"),
        ("task4", "priority", "max_retries_exceeded"),
        ("task5", "main", "invalid_payload"),
    ]

    for name, queue, reason in tasks_data:
        task = Task(name=name)
        task.fail(error="Failed")
        dlq.add_failed_task(task, original_queue=queue, reason=reason)

    print_subheader("Filter by Reason: timeout")
    timeout_tasks = dlq.inspect(reason="timeout")
    print(f"Found: {len(timeout_tasks)} tasks")
    for t in timeout_tasks:
        print(f"   - {t.task.name} from {t.original_queue}")

    print_subheader("Filter by Queue: priority")
    priority_tasks = dlq.inspect(queue_name="priority")
    print(f"Found: {len(priority_tasks)} tasks")
    for t in priority_tasks:
        print(f"   - {t.task.name} ({t.reason})")

    print_subheader("Combined Filter: main + max_retries_exceeded")
    specific_tasks = dlq.inspect(queue_name="main", reason="max_retries_exceeded")
    print(f"Found: {len(specific_tasks)} tasks")
    for t in specific_tasks:
        print(f"   - {t.task.name}")


def demo_replay():
    """Demo 4: Replaying failed tasks."""
    print_header("Demo 4: Replaying Failed Tasks")

    dlq = DeadLetterQueue()

    # Create a task with exhausted retries
    task = Task(
        name="critical_task",
        payload={"data": "important"},
        max_retries=3,
        priority=5,
    )
    task.retry_count = 3
    task.fail(error="Service unavailable", error_type="ConnectionError")

    dead_letter = dlq.add_failed_task(
        task=task,
        original_queue="critical",
        reason="max_retries_exceeded",
        retry_count=3,
    )

    print(f"📝 Original task:")
    print(f"   Name: {task.name}")
    print(f"   Status: {task.status}")
    print(f"   Retries: {task.retry_count}/{task.max_retries}")
    print(f"   Priority: {task.priority}")
    print(f"   DLQ entry ID: {dead_letter.id}")

    print_subheader("Replay with reset_retries=True")

    replayed = dlq.replay(
        replay_id=dead_letter.id,
        reset_retries=True,
        new_max_retries=10,
        new_priority=1,
    )

    print(f"✅ Replay completed")
    print(f"   New task ID: {replayed.id}")
    print(f"   Status: {replayed.status}")
    print(f"   Retries: {replayed.retry_count}/{replayed.max_retries}")
    print(f"   Priority: {replayed.priority}")

    print_subheader("Replay Metadata")
    print(f"   Original failed at: {replayed.metadata.get('dlq_original_failed_at')}")
    print(f"   Replay reason: {replayed.metadata.get('dlq_reason')}")
    print(f"   Original retry count: {replayed.metadata.get('dlq_original_retry_count')}")

    print_subheader("DLQ Status After Replay")
    print(f"   DLQ count: {dlq.count()}")


def demo_batch_operations():
    """Demo 5: Batch operations (replay/purge all or filtered)."""
    print_header("Demo 5: Batch Operations")

    dlq = DeadLetterQueue()

    # Add multiple tasks
    for i in range(10):
        task = Task(name=f"batch_task_{i}")
        task.fail(error=f"Error {i}")
        reason = "timeout" if i % 2 == 0 else "max_retries_exceeded"
        dlq.add_failed_task(task, reason=reason)

    print(f"📊 Initial DLQ count: {dlq.count()}")

    # Replay filtered tasks (only timeout)
    print_subheader("Replay All Timeout Tasks")
    replayed = dlq.replay_filtered(reason="timeout", reset_retries=True)
    print(f"✅ Replayed {len(replayed)} timeout tasks")
    print(f"📊 DLQ count after replay: {dlq.count()}")

    # Purge remaining tasks
    print_subheader("Purge All Remaining Tasks")
    purged = dlq.purge_all()
    print(f"🗑️  Purged {purged} tasks")
    print(f"📊 DLQ count after purge: {dlq.count()}")


def demo_statistics():
    """Demo 6: Statistics and monitoring."""
    print_header("Demo 6: Statistics and Monitoring")

    dlq = DeadLetterQueue()

    # Add diverse failure scenarios
    scenarios = [
        ("api_task_1", "main", "timeout", "TimeoutError"),
        ("api_task_2", "main", "timeout", "TimeoutError"),
        ("api_task_3", "main", "max_retries_exceeded", "ValueError"),
        ("db_task_1", "database", "timeout", "TimeoutError"),
        ("db_task_2", "database", "permission_denied", "PermissionError"),
        ("report_task", "reports", "max_retries_exceeded", "OSError"),
        ("email_task_1", "notifications", "service_not_available", "ConnectionError"),
        ("email_task_2", "notifications", "service_not_available", "ConnectionError"),
    ]

    for name, queue, reason, error_type in scenarios:
        task = Task(name=name)
        task.fail(error=error_type, error_type=error_type)
        dlq.add_failed_task(task, original_queue=queue, reason=reason, error_type=error_type)

    print_subheader("Full Statistics")
    stats = dlq.get_statistics()
    print(f"   Total failed tasks: {stats['total_count']}")
    print(f"   By queue:")
    for queue, count in stats['queues'].items():
        print(f"      - {queue:15} : {count}")
    print(f"   By reason:")
    for reason, count in stats['reasons'].items():
        print(f"      - {reason:25} : {count}")
    print(f"   By error type:")
    for error_type, count in stats['errors'].items():
        print(f"      - {error_type:20} : {count}")

    print_subheader("Count by Specific Criteria")
    print(f"   Total: {dlq.count()}")
    print(f"   Timeout tasks: {dlq.count_by_reason('timeout')}")
    print(f"   Main queue tasks: {dlq.count_by_queue('main')}")
    print(f"   Notifications queue tasks: {dlq.count_by_queue('notifications')}")


def demo_complete_workflow():
    """Demo 7:Complete workflow with realistic scenario."""
    print_header("Demo 7: Complete Realistic Workflow")

    print("Simulating a payment processing system with retry and DLQ handling...")

    dlq = DeadLetterQueue()

    # Simulate multiple payment failures
    print_subheader("Processing Payments (with failures)")
    for i in range(1, 11):
        payment_id = f"PAY-{1000+i}"
        task = Task(
            name=f"process_payment_{payment_id}",
            payload={
                "payment_id": payment_id,
                "amount": 99.99,
                "currency": "USD",
            },
            priority=1,  # High priority for payments
        )

        # Simulate different failure scenarios
        if i % 3 == 0:
            # Service timeout
            task.fail(error="Payment gateway timeout", error_type="TimeoutError")
            reason = "timeout"
        elif i % 5 == 0:
            # Validation error
            task.fail(error="Invalid card number", error_type="ValueError")
            reason = "invalid_payload"
        else:
            # Payment gateway error
            task.fail(error="Payment declined", error_type="PaymentError")
            reason = "max_retries_exceeded"

        # Add to DLQ
        dead_letter = dlq.add_failed_task(
            task=task,
            original_queue="payments",
            reason=reason,
            retry_count=3,
        )
        print(f"   ❌ Payment {payment_id} failed → {reason}")

    print_subheader("Analyzing Failures")
    stats = dlq.get_statistics()
    print(f"   Total failed payments: {stats['total_count']}")
    print(f"   Failure reasons:")
    for reason, count in stats['reasons'].items():
        print(f"      - {reason.replace('_', ' ').title()}: {count}")

    print_subheader("Reviewing Specific Failures")
    print("   Tasks with validation errors (likely user issue):")
    invalid_tasks = dlq.inspect(reason="invalid_payload")
    for t in invalid_tasks:
        print(f"      - {t.task.name}")

    print_subheader("Taking Action")
    print("   Replaying timeout tasks (might be transient):")
    timeout_tasks = dlq.replay_filtered(reason="timeout", reset_retries=True)
    print(f"      ✓ Replayed {len(timeout_tasks)} tasks")
    for task in timeout_tasks:
        print(f"        - {task.name} (priority: {task.priority}, retries: {task.max_retries})")

    print("   Purging invalid payload tasks (need user fix):")
    purged = dlq.purge_filtered(reason="invalid_payload")
    print(f"      ✓ Purged {purged} tasks")

    print_subheader("Final Status")
    print(f"   Remaining in DLQ: {dlq.count()}")
    print(f"   Tasks to retry: {len(timeout_tasks)}")
    print(f"   Tasks removed: {purged}")


def demo_serialization():
    """Demo 8: Serialization and deserialization."""
    print_header("Demo 8: Serialization")

    # Create a complex dead letter task
    task = Task(
        name="complex_task",
        payload={
            "nested": {"data": {"values": [1, 2, 3]}},
            "timestamp": datetime.utcnow().isoformat(),
        },
        metadata={
            "attempt": 5,
            "worker": "worker1",
        },
    )
    task.fail(error="Complex failure", error_type="RuntimeError")

    dead_letter = DeadLetterTask(
        task=task,
        original_queue="complex",
        reason="max_retries_exceeded",
        error_message="Failed after 5 attempts",
        error_type="RuntimeError",
        retry_count=5,
        metadata={
            "worker_id": "worker-123",
            "hostname": "server-01",
            "traceback": "Frame 1\nFrame 2\nFrame 3",
        },
    )

    print(f"✅ Created DeadLetterTask:")
    print(f"   ID: {dead_letter.id}")
    print(f"   Task: {dead_letter.task.name}")
    print(f"   Reason: {dead_letter.reason}")

    print_subheader("Serializing to Dictionary")
    data_dict = dead_letter.to_dict()
    print(f"   ✅ Serialized to {len(data_dict)} fields")
    print(f"   Sample fields: id, task, reason, failed_at, retry_count")

    print_subheader("Deserializing Back")
    restored = DeadLetterTask.from_dict(data_dict)
    print(f"   ✅ Restored DeadLetterTask:")
    print(f"   ID: {restored.id}")
    print(f"   Task: {restored.task.name}")
    print(f"   Reason: {restored.reason}")
    print(f"   Failed at: {restored.failed_at}")

    # Verify match
    assert str(restored.id) == str(dead_letter.id)
    assert restored.task.name == dead_letter.task.name
    assert restored.reason == dead_letter.reason
    print("   ✅ Serialization/Deserialization verified!")


def main():
    """Run all demonstrations."""
    print_header("Dead Letter Queue Demonstration")
    print("This demo showcases the complete DLQ functionality.")
    print("Each demo builds on a fresh DLQ instance.")

    demos = [
        ("Basic Operations", demo_basic_operations),
        ("Adding Multiple Tasks", demo_adding_multiple_tasks),
        ("Filtering", demo_filtering),
        ("Replaying Tasks", demo_replay),
        ("Batch Operations", demo_batch_operations),
        ("Statistics", demo_statistics),
        ("Complete Workflow", demo_complete_workflow),
        ("Serialization", demo_serialization),
    ]

    for i, (name, demo_func) in enumerate(demos, 1):
        print(f"\n\n{'#'*70}")
        print(f"# DEMO {i}/{len(demos)}: {name}")
        print(f"{'#'*70}")
        try:
            demo_func()
            print(f"\n✅ Demo {i} completed successfully!")
        except Exception as e:
            print(f"\n❌ Demo {i} failed: {e}")
            import traceback
            traceback.print_exc()

    print_header("All Demos Completed")
    print("The Dead Letter Queue system is ready for production use!")
    print("\nKey Features Demonstrated:")
    print("  ✅ Add failed tasks to DLQ")
    print("  ✅ Inspect and filter failed tasks")
    print("  ✅ Replay tasks back to main queue")
    print("  ✅ Batch operations (replay/purge)")
    print("  ✅ Statistics and monitoring")
    print("  ✅ Serialization and persistence support")
    print("  ✅ Complete realistic workflows")
    print("\nFor more information, see:")
    print("  - DLQ_IMPLEMENTATION_SUMMARY.md")
    print("  - DLQ_QUICK_REFERENCE.md")


if __name__ == "__main__":
    main()
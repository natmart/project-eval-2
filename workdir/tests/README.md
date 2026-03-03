# Test Suite for DLQ and Scheduler

This directory contains comprehensive tests for the Dead Letter Queue (DLQ) and Cron Scheduler modules.

## Test Files

### test_dlq.py
Tests for the Dead Letter Queue (DLQ) system covering:
- **DeadLetterTask** dataclass functionality (7 tests)
  - Creation with various attributes
  - Serialization/deserialization
  - Metadata handling

- **MemoryDLQBackend** operations (10 tests)
  - Thread-safe add/get/remove operations
  - Filtering by reason and/or queue name
  - Purge operations (all and filtered)
  - Statistics generation

- **DeadLetterQueue** interface (18 tests)
  - Adding tasks (extracts error info from result or deprecated error field)
  - Inspecting (all, with filters)
  - Replay (single, filtered, with/without retry reset)
  - Purge (single, all, filtered)
  - Statistics and counting
  - Custom backend support

- **Backwards compatibility** (2 tests)
  - Handling deprecated error field
  - Result.error takes precedence over error field

**Total**: ~37 test classes covering all DLQ operations

### test_scheduler.py
Tests for the Cron Scheduler covering:
- **CronSchedule** parsing and matching (25+ tests)
  - Wildcards
  - Specific values
  - Intervals (*/n)
  - Ranges (n-m)
  - Lists (n,m,o)
  - Ranges with intervals (n-m/o)
  - Named days of week (MON-FRI)
  - Named months (JAN, FEB, etc.)
  - Invalid expressions
  - should_run() with various schedules
  - next_run_time() calculation
  - Helper methods (matches_minute, matches_hour, etc.)

- **ScheduledJob** dataclass (5 tests)
  - Creation and attributes
  - update_next_run() with/without after parameter
  - Serialization with to_dict()

- **CronScheduler** operations (20+ tests)
  - Initialization (default and custom check interval)
  - Job management (add, remove, get, enable, disable)
  - Update job schedule
  - Clear all jobs
  - Get due jobs
  - Start/stop scheduler
  - Context manager support
  - Thread safety
  - Multiple independent schedulers

- **Schedule accuracy** tests (5 tests)
  - Year boundary handling
  - Leap year testing (Feb 29)
  - Month boundary handling
  - End of month scheduling
  - Specific time matching

- **Background thread** tests (6 tests)
  - Thread starts and stops correctly
  - Responds to stop events
  - Handles jobs with no tasks
  - Handles disabled jobs
  - Continues execution despite exceptions

**Total**: ~60 tests covering all scheduler functionality

## Running Tests

### Run all DLQ tests:
```bash
python tests/run_dlq_tests.py
```

### Run all Scheduler tests:
```bash
python tests/run_scheduler_tests.py
```

### Run with pytest directly:
```bash
pytest tests/test_dlq.py -v
pytest tests/test_scheduler.py -v
```

### Run specific test classes:
```bash
pytest tests/test_dlq.py::TestDeadLetterTask -v
pytest tests/test_scheduler.py::TestCronSchedule -v
```

## Test Coverage

Both test suites achieve comprehensive coverage of:

### DLQ Module
- DeadLetterTask: creation, serialization, retry info preservation
- DLQBackend: all abstract methods
- MemoryDLQBackend: thread-safety, CRUD operations, filtering
- DeadLetterQueue: add, inspect, replay, purge, stats

### Scheduler Module
- CronSchedule: parsing (all patterns), matching, next_run calculation
- ScheduledJob: creation, update_next_run, serialization
- CronScheduler: job lifecycle, background thread, context manager

## Notes

- Tests use pytest framework
- Thread-safety tests use actual threading
- Background thread tests include timing assertions
- All tests are independent and can be run in any order
- Tests verify both positive and negative scenarios
"""Example task handlers for CLI testing and demonstrations."""


def greet(payload):
    """Greet someone by name."""
    name = payload.get("name", "World")
    return f"Hello, {name}!"


def send_email(payload):
    """Send an email (simulated)."""
    to = payload.get("to")
    subject = payload.get("subject")
    body = payload.get("body", "")
    return {
        "status": "sent",
        "to": to,
        "subject": subject,
        "body_length": len(body)
    }


def process_data(payload):
    """Process data by doubling values."""
    data = payload.get("data", 0)
    result = data * 2
    return {"original": data, "processed": result}


def failing_task(payload):
    """A task that always fails."""
    raise RuntimeError("This task always fails for demonstration purposes")


def flaky_task(payload):
    """A task that fails before succeeding."""
    import random
    if random.random() < 0.7:
        raise RuntimeError("Temporary failure for demonstration")
    return {"status": "success"}


if __name__ == "__main__":
    # Register tasks when module is run directly
    from python_task_queue import get_registry
    
    registry = get_registry()
    registry.register("greet")(greet)
    registry.register("send_email")(send_email)
    registry.register("process_data")(process_data)
    registry.register("failing_task")(failing_task)
    registry.register("flaky_task")(flaky_task)
    
    print("Tasks registered successfully!")
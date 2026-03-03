#!/usr/bin/env python3
"""Simple test to verify CLI can be imported."""

import sys

# Add workdir to path so we can import the package
sys.path.insert(0, '.')

try:
    print("Testing CLI import...")
    from python_task_queue.cli import cli
    print("✓ CLI imported successfully")
    
    # Test that it's a Click command group
    import click
    assert isinstance(cli, click.Group), "CLI should be a Click Group"
    print("✓ CLI is a proper Click Group")
    
    # List available commands
    print(f"✓ Available commands: {list(cli.list_commands(None))}")
    
    print("\n✅ All CLI import tests passed!")
    sys.exit(0)
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
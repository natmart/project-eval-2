"""
Tests for the retry policy system.
"""

import time
import random
from datetime import datetime
from typing import Type
from unittest.mock import Mock, patch

import pytest

from python_task_queue.retry import (
    RetryStrategy,
    RetryDecisionReason,
    RetryDecision,
    RetryPolicyConfig,
    ConstantRetryStrategy,
    ExponentialRetryStrategy,
    ExponentialJitterRetryStrategy,
    RetryPolicy,
    simple_retry_policy,
    aggressive_retry_policy,
    conservative_retry_policy,
    network_retry_policy,
    no_retry_policy,
)
from python_task_queue.models import Task, TaskStatus


class TestRetryStrategy:
    """Tests for RetryStrategy enum."""

    def test_strategy_enum_values(self):
        """Test that all strategy enum values are defined."""
        assert RetryStrategy.CONSTANT.value == "constant"
        assert RetryStrategy.EXPONENTIAL.value == "exponential"
        assert RetryStrategy.EXPONENTIAL_JITTER.value == "exponential_jitter"

    def test_strategy_string_representation(self):
        """Test string representation of strategies."""
        assert str(RetryStrategy.CONSTANT) == "constant"
        assert str(RetryStrategy.EXPONENTIAL) == "exponential"
        assert str(RetryStrategy.EXPONENTIAL_JITTER) == "exponential_jitter"


class TestRetryDecisionReason:
    """Tests for RetryDecisionReason enum."""

    def test_reason_enum_values(self):
        """Test that all reason enum values are defined."""
        assert RetryDecisionReason.WITHIN_MAX_RETRIES.value == "within_max_retries"
        assert RetryDecisionReason.RETRYABLE_EXCEPTION.value == "retryable_exception"
        assert RetryDecisionReason.MAX_RETRIES_EXCEEDED.value == "max_retries_exceeded"
        assert RetryDecisionReason.NON_RETRYABLE_EXCEPTION.value == "non_retryable_exception"


class TestRetryDecision:
    """Tests for RetryDecision dataclass."""

    def test_decision_creation(self):
        """Test creating a retry decision."""
        decision = RetryDecision(
            should_retry=True, delay=1.5, reason=RetryDecisionReason.WITHIN_MAX_RETRIES, attempt_number=0
        )
        assert decision.should_retry is True
        assert decision.delay == 1.5
        assert decision.reason == RetryDecisionReason.WITHIN_MAX_RETRIES
        assert decision.attempt_number == 0

    def test_negative_decision(self):
        """Test creating a negative retry decision."""
        decision = RetryDecision(
            should_retry=False, delay=0.0, reason=RetryDecisionReason.MAX_RETRIES_EXCEEDED, attempt_number=5
        )
        assert decision.should_retry is False
        assert decision.delay == 0.0

    def test_decision_representation(self):
        """Test string representation of decision."""
        decision = RetryDecision(
            should_retry=True, delay=1.5, reason=RetryDecisionReason.WITHIN_MAX_RETRIES, attempt_number=0
        )
        repr_str = repr(decision)
        assert "RETRY" in repr_str
        assert "1.50s" in repr_str
        assert "within_max_retries" in repr_str
        assert "attempt=0" in repr_str


class TestRetryPolicyConfig:
    """Tests for RetryPolicyConfig dataclass."""

    def test_default_config(self):
        """Test creating config with default values."""
        config = RetryPolicyConfig()
        assert config.max_retries == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 60.0
        assert config.strategy == RetryStrategy.EXPONENTIAL
        assert config.base_multiplier == 2.0
        assert config.jitter_factor == 0.1
        assert config.backoff_multiplier == 2.0

    def test_custom_config(self):
        """Test creating config with custom values."""
        config = RetryPolicyConfig(
            max_retries=5, initial_delay=2.0, max_delay=120.0, strategy=RetryStrategy.CONSTANT
        )
        assert config.max_retries == 5
        assert config.initial_delay == 2.0
        assert config.max_delay == 120.0
        assert config.strategy == RetryStrategy.CONSTANT

    def test_invalid_max_retries(self):
        """Test that negative max_retries raises ValueError."""
        with pytest.raises(ValueError, match="max_retries must be >= 0"):
            RetryPolicyConfig(max_retries=-1)

    def test_invalid_initial_delay(self):
        """Test that negative initial_delay raises ValueError."""
        with pytest.raises(ValueError, match="initial_delay must be >= 0"):
            RetryPolicyConfig(initial_delay=-1.0)

    def test_invalid_max_delay(self):
        """Test that negative max_delay raises ValueError."""
        with pytest.raises(ValueError, match="max_delay must be >= 0"):
            RetryPolicyConfig(max_delay=-1.0)

    def test_initial_delay_exceeds_max_delay(self):
        """Test that initial_delay > max_delay raises ValueError."""
        with pytest.raises(ValueError, match="initial_delay .* exceeds max_delay"):
            RetryPolicyConfig(initial_delay=100.0, max_delay=50.0)

    def test_invalid_base_multiplier(self):
        """Test that non-positive base_multiplier raises ValueError."""
        with pytest.raises(ValueError, match="base_multiplier must be > 0"):
            RetryPolicyConfig(base_multiplier=0.0)

    def test_invalid_jitter_factor(self):
        """Test that jitter_factor outside [0, 1] raises ValueError."""
        with pytest.raises(ValueError, match="jitter_factor must be between 0 and 1"):
            RetryPolicyConfig(jitter_factor=-0.1)

        with pytest.raises(ValueError, match="jitter_factor must be between 0 and 1"):
            RetryPolicyConfig(jitter_factor=1.5)

    def test_invalid_backoff_multiplier(self):
        """Test that non-positive backoff_multiplier raises ValueError."""
        with pytest.raises(ValueError, match="backoff_multiplier must be > 0"):
            RetryPolicyConfig(backoff_multiplier=0.0)


class TestConstantRetryStrategy:
    """Tests for ConstantRetryStrategy class."""

    def test_constant_delay(self):
        """Test that constant strategy returns same delay for all attempts."""
        strategy = ConstantRetryStrategy()
        config = RetryPolicyConfig(initial_delay=5.0, max_delay=100.0)

        delays = [strategy.calculate_delay(attempt, config) for attempt in range(10)]
        assert all(delay == 5.0 for delay in delays)

    def test_constant_delay_capped(self):
        """Test that constant delay is capped at max_delay."""
        strategy = ConstantRetryStrategy()
        config = RetryPolicyConfig(initial_delay=100.0, max_delay=50.0)

        delay = strategy.calculate_delay(0, config)
        assert delay == 50.0

    def test_constant_delay_zero(self):
        """Test constant delay with zero initial_delay."""
        strategy = ConstantRetryStrategy()
        config = RetryPolicyConfig(initial_delay=0.0, max_delay=100.0)

        delay = strategy.calculate_delay(0, config)
        assert delay == 0.0


class TestExponentialRetryStrategy:
    """Tests for ExponentialRetryStrategy class."""

    def test_exponential_delays(self):
        """Test exponential delay calculation."""
        strategy = ExponentialRetryStrategy()
        config = RetryPolicyConfig(initial_delay=1.0, backoff_multiplier=2.0, max_delay=1000.0)

        delays = [strategy.calculate_delay(attempt, config) for attempt in range(5)]
        assert delays[0] == 1.0
        assert delays[1] == 2.0
        assert delays[2] == 4.0
        assert delays[3] == 8.0
        assert delays[4] == 16.0

    def test_exponential_delays_with_multiplier_3(self):
        """Test exponential delay with different multiplier."""
        strategy = ExponentialRetryStrategy()
        config = RetryPolicyConfig(initial_delay=1.0, backoff_multiplier=3.0, max_delay=1000.0)

        delays = [strategy.calculate_delay(attempt, config) for attempt in range(4)]
        assert delays[0] == 1.0
        assert delays[1] == 3.0
        assert delays[2] == 9.0
        assert delays[3] == 27.0

    def test_exponential_delays_capped(self):
        """Test that exponential delays are capped at max_delay."""
        strategy = ExponentialRetryStrategy()
        config = RetryPolicyConfig(initial_delay=10.0, backoff_multiplier=2.0, max_delay=30.0)

        delays = [strategy.calculate_delay(attempt, config) for attempt in range(5)]
        assert delays[0] == 10.0
        assert delays[1] == 20.0
        assert delays[2] == 30.0  # Capped
        assert delays[3] == 30.0  # Capped
        assert delays[4] == 30.0  # Capped


class TestExponentialJitterRetryStrategy:
    """Tests for ExponentialJitterRetryStrategy class."""

    def test_jitter_within_bounds(self):
        """Test that jitter keeps delays within expected bounds."""
        strategy = ExponentialJitterRetryStrategy()
        config = RetryPolicyConfig(initial_delay=10.0, jitter_factor=0.1, max_delay=1000.0)

        # Run multiple trials to verify bounds
        for attempt in range(5):
            delays = [strategy.calculate_delay(attempt, config) for _ in range(100)]

            # Expected base delay
            exp_strategy = ExponentialRetryStrategy()
            base_delay = exp_strategy.calculate_delay(attempt, config)

            # All delays should be within [base * 0.9, base * 1.1]
            min_expected = base_delay * (1.0 - config.jitter_factor)
            max_expected = base_delay * (1.0 + config.jitter_factor)

            assert all(min_expected <= delay <= max_expected for delay in delays)

    def test_jitter_zero_diversity(self):
        """Test that zero jitter_factor reduces to exponential."""
        strategy = ExponentialJitterRetryStrategy()
        config = RetryPolicyConfig(initial_delay=1.0, jitter_factor=0.0, max_delay=1000.0)

        exp_strategy = ExponentialRetryStrategy()

        for attempt in range(5):
            jitter_delay = strategy.calculate_delay(attempt, config)
            exp_delay = exp_strategy.calculate_delay(attempt, config)
            assert jit_delay == exp_delay

    def test_jitter_high_diversity(self):
        """Test that high jitter_factor increases delay diversity."""
        strategy = ExponentialJitterRetryStrategy()
        config_high = RetryPolicyConfig(initial_delay=10.0, jitter_factor=0.5, max_delay=1000.0)
        config_low = RetryPolicyConfig(initial_delay=10.0, jitter_factor=0.05, max_delay=1000.0)

        # Sample delays
        delays_high = [strategy.calculate_delay(2, config_high) for _ in range(100)]
        delays_low = [strategy.calculate_delay(2, config_low) for _ in range(100)]

        # High jitter should have more variance
        variance_high = sum((d - sum(delays_high) / len(delays_high)) ** 2 for d in delays_high) / len(delays_high)
        variance_low = sum((d - sum(delays_low) / len(delays_low)) ** 2 for d in delays_low) / len(delays_low)

        assert variance_high > variance_low

    def test_jitter_capped(self):
        """Test that jitter delays are also capped at max_delay."""
        strategy = ExponentialJitterRetryStrategy()
        config = RetryPolicyConfig(initial_delay=10.0, backoff_multiplier=2.0, jitter_factor=0.5, max_delay=15.0)

        # Generate many delays at high attempt number
        delays = [strategy.calculate_delay(10, config) for _ in range(50)]
        assert all(delay <= 15.0 for delay in delays)

    def test_jitter_non_negative(self):
        """Test that jitter never produces negative delays."""
        strategy = ExponentialJitterRetryStrategy()
        config = RetryPolicyConfig(initial_delay=0.1, jitter_factor=1.0, max_delay=1000.0)

        delays = [strategy.calculate_delay(0, config) for _ in range(100)]
        assert all(delay >= 0 for delay in delays)


class TestRetryPolicy:
    """Tests for RetryPolicy class."""

    @pytest.fixture
    def sample_task(self):
        """Create a sample task for testing."""
        return Task(name="test_task", payload={"key": "value"})

    @pytest.fixture
    def failed_task(self):
        """Create a task that has failed once."""
        task = Task(name="failed_task", payload={"key": "value"})
        task.status = TaskStatus.FAILED
        task.retry_count = 1
        return task

    def test_retry_policy_creation(self, sample_task):
        """Test creating a retry policy."""
        policy = RetryPolicy(max_retries=3)
        decision = policy.get_retry_decision(sample_task, Exception("test"))
        assert decision.attempt_number == 0

    def test_should_retry_within_limit(self, failed_task):
        """Test should_retry returns True within max_retries."""
        policy = RetryPolicy(max_retries=5)
        failed_task.retry_count = 2
        assert policy.should_retry(failed_task, Exception("test")) is True

    def test_should_retry_exceeds_limit(self, failed_task):
        """Test should_retry returns False when max_retries exceeded."""
        policy = RetryPolicy(max_retries=3)
        failed_task.retry_count = 3
        assert policy.should_retry(failed_task, Exception("test")) is False

    def test_no_retries_policy(self, sample_task):
        """Test policy with max_retries=0 never retries."""
        policy = RetryPolicy(max_retries=0)
        assert policy.should_retry(sample_task, Exception("test")) is False

    def test_retryable_exceptions_allowed(self, failed_task):
        """Test that retryable exceptions allow retry."""
        policy = RetryPolicy(
            max_retries=5, retryable_exceptions=[ValueError, KeyError]
        )
        assert policy.should_retry(failed_task, ValueError("test")) is True
        assert policy.should_retry(failed_task, KeyError("test")) is True

    def test_retryable_exceptions_filter_others(self, failed_task):
        """Test that non-listed exceptions are not retried when retryable_exceptions set."""
        policy = RetryPolicy(max_retries=5, retryable_exceptions=[ValueError])
        assert policy.should_retry(failed_task, ValueError("test")) is True
        assert policy.should_retry(failed_task, RuntimeError("test")) is False

    def test_non_retryable_exceptions_block(self, failed_task):
        """Test that non_retryable_exceptions block retry."""
        policy = RetryPolicy(non_retryable_exceptions=[ValueError])
        assert policy.should_retry(failed_task, ValueError("test")) is False
        assert policy.should_retry(failed_task, RuntimeError("test")) is True

    def test_non_retryable_takes_precedence(self, failed_task):
        """Test that non_retryable_exceptions takes precedence."""
        policy = RetryPolicy(
            retryable_exceptions=[Exception], non_retryable_exceptions=[ValueError]
        )
        # Exception is retryable, but ValueError is specifically non-retryable
        assert policy.should_retry(failed_task, ValueError("test")) is False
        assert policy.should_retry(failed_task, RuntimeError("test")) is True

    def test_all_exceptions_retryable_by_default(self, failed_task):
        """Test that all exceptions are retryable by default."""
        policy = RetryPolicy(max_retries=5)
        assert policy.should_retry(failed_task, ValueError("test")) is True
        assert policy.should_retry(failed_task, RuntimeError("test")) is True
        assert policy.should_retry(failed_task, TypeError("test")) is True
        assert policy.should_retry(failed_task, KeyError("test")) is True

    def test_get_retry_decision_returns_decision(self, failed_task):
        """Test that get_retry_decision returns a RetryDecision object."""
        policy = RetryPolicy(max_retries=5)
        decision = policy.get_retry_decision(failed_task, Exception("test"))
        assert isinstance(decision, RetryDecision)
        assert hasattr(decision, "should_retry")
        assert hasattr(decision, "delay")
        assert hasattr(decision, "reason")
        assert hasattr(decision, "attempt_number")

    def test_get_retry_decision_max_retries_reason(self, failed_task):
        """Test that decision reason is correct for max_retries."""
        policy = RetryPolicy(max_retries=3)
        failed_task.retry_count = 3
        decision = policy.get_retry_decision(failed_task, Exception("test"))
        assert decision.should_retry is False
        assert decision.reason == RetryDecisionReason.MAX_RETRIES_EXCEEDED

    def test_get_retry_decision_retryable_reason(self, failed_task):
        """Test that decision reason is correct for retryable exception."""
        policy = RetryPolicy(max_retries=5, retryable_exceptions=[ValueError])
        failed_task.retry_count = 1
        decision = policy.get_retry_decision(failed_task, ValueError("test"))
        assert decision.should_retry is True
        assert decision.reason in (
            RetryDecisionReason.WITHIN_MAX_RETRIES,
            RetryDecisionReason.RETRYABLE_EXCEPTION,
        )

    def test_get_retry_decision_non_retryable_reason(self, failed_task):
        """Test that decision reason is correct for non-retryable exception."""
        policy = RetryPolicy(max_retries=5, retryable_exceptions=[ValueError])
        failed_task.retry_count = 1
        decision = policy.get_retry_decision(failed_task, RuntimeError("test"))
        assert decision.should_retry is False
        assert decision.reason == RetryDecisionReason.NON_RETRYABLE_EXCEPTION

    def test_custom_retry_function_allowed(self, failed_task):
        """Test custom retry function that allows retry."""
        def custom_func(task, exception):
            return isinstance(exception, TemporaryError)

        policy = RetryPolicy(
            max_retries=1, should_retry_func=custom_func
        )

        class TemporaryError(Exception):
            pass

        class PermanentError(Exception):
            pass

        assert policy.should_retry(failed_task, TemporaryError("test")) is True
        assert policy.should_retry(failed_task, PermanentError("test")) is False

    def test_custom_retry_function_denied(self, failed_task):
        """Test custom retry function that denies retry."""
        def custom_func(task, exception):
            return False

        policy = RetryPolicy(max_retries=5, should_retry_func=custom_func)
        assert policy.should_retry(failed_task, Exception("test")) is False

    def test_custom_retry_function_exception_handling(self, failed_task):
        """Test that exceptions in custom function are handled gracefully."""
        def custom_func(task, exception):
            raise RuntimeError("Custom function error")

        policy = RetryPolicy(max_retries=5, should_retry_func=custom_func)
        # Should fall back to default policy and return True
        assert policy.should_retry(failed_task, Exception("test")) is True

    def test_constant_strategy_delays(self, failed_task):
        """Test constant strategy delays."""
        policy = RetryPolicy(
            max_retries=5,
            strategy=RetryStrategy.CONSTANT,
            initial_delay=10.0,
            max_delay=100.0,
        )
        delays = [policy.get_retry_delay(attempt) for attempt in range(5)]
        assert all(delay == 10.0 for delay in delays)

    def test_exponential_strategy_delays(self, failed_task):
        """Test exponential strategy delays."""
        policy = RetryPolicy(
            max_retries=5,
            strategy=RetryStrategy.EXPONENTIAL,
            initial_delay=1.0,
            backoff_multiplier=2.0,
            max_delay=1000.0,
        )
        delays = [policy.get_retry_delay(attempt) for attempt in range(5)]
        assert delays[0] == 1.0
        assert delays[1] == 2.0
        assert delays[2] == 4.0
        assert delays[3] == 8.0
        assert delays[4] == 16.0

    def test_exponential_jitter_strategy_delays(self, failed_task):
        """Test exponential jitter strategy delays vary."""
        # Set random seed for predictable testing
        random.seed(42)

        policy = RetryPolicy(
            max_retries=5,
            strategy=RetryStrategy.EXPONENTIAL_JITTER,
            initial_delay=10.0,
            jitter_factor=0.5,
            max_delay=1000.0,
        )

        # Get delays for same attempt multiple times
        delays = [policy.get_retry_delay(2) for _ in range(100)]

        # Delays should vary (not all identical)
        assert len(set(delays)) > 50  # Most should be different

        # But should be within reasonable bounds
        exp delay = 10.0 * 2.0 ** 2  # 40.0
        min_expected = 40.0 * 0.5
        max_expected = 40.0 * 1.5
        assert all(min_expected <= delay <= max_expected for delay in delays)

    def test_get_retry_schedule(self):
        """Test getting retry schedule."""
        policy = RetryPolicy(
            max_retries=5,
            strategy=RetryStrategy.EXPONENTIAL,
            initial_delay=1.0,
            backoff_multiplier=2.0,
            max_delay=1000.0,
        )
        schedule = policy.get_retry_schedule()
        assert len(schedule) == 5
        assert schedule[0] == (0, 1.0)
        assert schedule[1] == (1, 2.0)
        assert schedule[2] == (2, 4.0)
        assert schedule[3] == (3, 8.0)
        assert schedule[4] == (4, 16.0)

    def test_get_retry_schedule_custom_max_attempts(self):
        """Test getting retry schedule with custom max attempts."""
        policy = RetryPolicy(max_retries=10)
        schedule = policy.get_retry_schedule(max_attempts=3)
        assert len(schedule) == 3

    def test_copy_policy_with_overrides(self):
        """Test copying policy with overrides."""
        original = RetryPolicy(
            max_retries=3,
            strategy=RetryStrategy.CONSTANT,
            initial_delay=1.0,
            retryable_exceptions=[ValueError],
        )

        copy = original.copy(max_retries=10, initial_delay=5.0)

        # Original should be unchanged
        assert original.config.max_retries == 3
        assert original.config.initial_delay == 1.0
        assert original.config.strategy == RetryStrategy.CONSTANT

        # Copy should have overrides
        assert copy.config.max_retries == 10
        assert copy.config.initial_delay == 5.0
        assert copy.config.strategy == RetryStrategy.CONSTANT
        assert ValueError in original.retryable_exceptions
        assert ValueError in copy.retryable_exceptions

    def test_copy_policy_no_overrides(self):
        """Test copying policy without overrides."""
        original = RetryPolicy(max_retries=5, initial_delay=2.0)
        copy = original.copy()

        assert copy.config.max_retries == original.config.max_retries
        assert copy.config.initial_delay == original.config.initial_delay
        assert copy.config.strategy == original.config.strategy

    def test_policy_representation(self):
        """Test string representation of policy."""
        policy = RetryPolicy(
            max_retries=3,
            strategy=RetryStrategy.EXPONENTIAL,
            initial_delay=1.0,
            max_delay=60.0,
        )
        repr_str = repr(policy)
        assert "RetryPolicy" in repr_str
        assert "exponential" in repr_str
        assert "max_retries=3" in repr_str
        assert "initial_delay=1.0s" in repr_str
        assert "max_delay=60.0s" in repr_str

    def test_policy_with_config_object(self):
        """Test creating policy with RetryPolicyConfig object."""
        config = RetryPolicyConfig(
            max_retries=7,
            initial_delay=2.0,
            max_delay=120.0,
            strategy=RetryStrategy.EXPONENTIAL_JITTER,
        )
        policy = RetryPolicy(config=config)

        assert policy.config == config
        assert policy.config.max_retries == 7
        assert policy.config.initial_delay == 2.0
        assert policy.config.strategy == RetryStrategy.EXPONENTIAL_JITTER

    def test_config_overrides_config_object(self):
        """Test that individual params override config object."""
        config = RetryPolicyConfig(max_retries=5)
        # If config is provided, individual params should be ignored
        # (this is by design in __init__)
        policy = RetryPolicy(config=config, max_retries=10)
        assert policy.config.max_retries == 5  # Config object takes precedence

    def test_task_status_completed_no_retry(self):
        """Test that completed tasks are not retried."""
        task = Task(name="completed_task")
        task.status = TaskStatus.COMPLETED
        task.retry_count = 0

        policy = RetryPolicy(max_retries=5)
        decision = policy.get_retry_decision(task, Exception("test"))

        assert decision.should_retry is False
        assert decision.reason == RetryDecisionReason.TASK_TERMINAL


class TestRetryPolicyWaitBeforeRetry:
    """Tests for wait_before_retry method."""

    @pytest.fixture
    def failed_task(self):
        """Create a task that has failed."""
        task = Task(name="failed_task")
        task.status = TaskStatus.FAILED
        task.retry_count = 1
        return task

    def test_wait_before_retry_waits(self, failed_task):
        """Test that wait_before_retry actually waits."""
        policy = RetryPolicy(max_retries=5, initial_delay=0.1)

        start = time.time()
        result = policy.wait_before_retry(failed_task, Exception("test"))
        elapsed = time.time() - start

        assert result is True
        assert elapsed >= 0.1

    def test_wait_before_retry_no_wait_on_no_retry(self, failed_task):
        """Test that wait_before_retry doesn't wait when no retry."""
        policy = RetryPolicy(max_retries=0)

        start = time.time()
        result = policy.wait_before_retry(failed_task, Exception("test"))
        elapsed = time.time() - start

        assert result is False
        assert elapsed < 0.1  # Should not wait

    @pytest.mark.patch("time.sleep")
    def test_wait_before_retry_logs_delay(self, mock_sleep, failed_task):
        """Test that wait_before_retry logs the delay."""
        policy = RetryPolicy(max_retries=5, initial_delay=1.5)

        with patch("python_task_queue.retry.logger") as mock_logger:
            policy.wait_before_retry(failed_task, Exception("test"))

            mock_logger.debug.assert_called_once()
            args = mock_logger.debug.call_args[0]
            assert "1.50s" in args[0]


class TestPreconfiguredPolicies:
    """Tests for pre-configured retry policy factory functions."""

    def test_simple_retry_policy(self):
        """Test simple_retry_policy factory."""
        policy = simple_retry_policy(max_retries=5)
        assert policy.config.max_retries == 5
        assert policy.config.strategy == RetryStrategy.EXPONENTIAL
        assert policy.config.initial_delay == 1.0
        assert policy.config.max_delay == 60.0

    def test_aggressive_retry_policy(self):
        """Test aggressive_retry_policy factory."""
        policy = aggressive_retry_policy(max_retries=10)
        assert policy.config.max_retries == 10
        assert policy.config.strategy == RetryStrategy.EXPONENTIAL_JITTER
        assert policy.config.initial_delay == 0.1
        assert policy.config.max_delay == 10.0
        assert policy.config.jitter_factor == 0.5

    def test_conservative_retry_policy(self):
        """Test conservative_retry_policy factory."""
        policy = conservative_retry_policy(max_retries=3)
        assert policy.config.max_retries == 3
        assert policy.config.strategy == RetryStrategy.EXPONENTIAL
        assert policy.config.initial_delay == 5.0
        assert policy.config.max_delay == 300.0
        assert policy.config.backoff_multiplier == 3.0

    def test_network_retry_policy(self):
        """Test network_retry_policy factory."""
        policy = network_retry_policy()
        assert policy.config.max_retries == 5
        assert policy.config.strategy == RetryStrategy.EXPONENTIAL_JITTER
        assert policy.config.initial_delay == 1.0
        assert policy.config.max_delay == 120.0
        assert policy.config.jitter_factor == 0.2

        # Check retryable exceptions
        assert ConnectionError in policy.retryable_exceptions
        assert TimeoutError in policy.retryable_exceptions
        assert OSError in policy.retryable_exceptions

    def test_no_retry_policy(self):
        """Test no_retry_policy factory."""
        policy = no_retry_policy()
        assert policy.config.max_retries == 0

        # Create a task and verify no retry
        task = Task(name="test_task")
        task.status = TaskStatus.FAILED
        task.retry_count = 0

        assert policy.should_retry(task, Exception("test")) is False


class Integration:
    """Integration tests for retry policy with real tasks."""

    def test_full_retry_lifecycle(self):
        """Test complete retry lifecycle from start to failure."""
        policy = RetryPolicy(
            max_retries=3,
            strategy=RetryStrategy.EXPONENTIAL,
            initial_delay=0.01,  # Very short for testing
            backoff_multiplier=2,
            max_delay=100.0,
        )

        task = Task(name="lifecycle_task", max_retries=3)

        # First failure
        task.start()
        task.fail("Error 1")
        task.retry_count = 0

        decision = policy.get_retry_decision(task, RuntimeError("Error 1"))
        assert decision.should_retry is True
        assert decision.delay == 0.01

        # Second failure
        task.retry()
        task.fail("Error 2")

        decision = policy.get_retry_decision(task, RuntimeError("Error 2"))
        assert decision.should_retry is True
        assert decision.delay == 0.02

        # Third failure
        task.retry()
        task.fail("Error 3")

        decision = policy.get_retry_decision(task, RuntimeError("Error 3"))
        assert decision.should_retry is True
        assert decision.delay == 0.04

        # Fourth failure (exceeds retries)
        task.retry()
        task.fail("Error 4")

        decision = policy.get_retry_decision(task, RuntimeError("Error 4"))
        assert decision.should_retry is False
        assert decision.reason == RetryDecisionReason.MAX_RETRIES_EXCEEDED

    def test_retry_with_exception_filtering(self):
        """Test retry lifecycle with exception filtering."""
        policy = RetryPolicy(
            max_retries=3,
            retryable_exceptions=[ConnectionError, TimeoutError],
            non_retryable_exceptions=[ValueError],
        )

        task = Task(name="filtered_task")
        task.status = TaskStatus.FAILED

        # Retryable exception
        assert policy.should_retry(task, ConnectionError("Network error"))
        assert policy.should_retry(task, TimeoutError("Timed out"))

        # Non-retryable exception (takes precedence)
        assert not policy.should_retry(task, ValueError("Invalid input"))

        # Other exceptions not in retryable list
        assert not policy.should_retry(task, RuntimeError("Other error"))

    def test_multiple_tasks_independent(self):
        """Test that multiple tasks have independent retry counts."""
        policy = RetryPolicy(max_retries=3, strategy=RetryStrategy.CONSTANT, initial_delay=1.0)

        task1 = Task(name="task1")
        task2 = Task(name="task2")

        task1.status = TaskStatus.FAILED
        task2.status = TaskStatus.FAILED

        task1.retry_count = 2
        task2.retry_count = 0

        # Task1 has used 2 retries, should get 1 more
        decision1 = policy.get_retry_decision(task1, Exception("test"))
        assert decision1.should_retry is True
        assert decision1.attempt_number == 2
        assert decision1.delay == 1.0

        # Task2 has used 0 retries, should get all 3
        decision2 = policy.get_retry_decision(task2, Exception("test"))
        assert decision2.should_retry is True
        assert decision2.attempt_number == 0
        assert decision2.delay == 1.0

    def test_retry_schedule_matches_delays(self):
        """Test that retry schedule matches actual delays."""
        policy = RetryPolicy(
            max_retries=5,
            strategy=RetryStrategy.EXPONENTIAL,
            initial_delay=2.0,
            backoff_multiplier=2.0,
            max_delay=1000.0,
        )

        schedule = policy.get_retry_schedule()

        for attempt, expected_delay in schedule:
            actual_delay = policy.get_retry_delay(attempt)
            assert actual_delay == expected_delay


# Run tests if this file is executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
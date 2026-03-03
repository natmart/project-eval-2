"""
Retry policy system for the Python Task Queue Library.

This module provides flexible retry strategies for failed tasks, including:
- Constant delay retry
- Exponential backoff retry
- Exponential backoff with jitter retry
"""

from __future__ import annotations

import random
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Set, Tuple, Type, Union, List, Any
from uuid import UUID

from python_task_queue.models import Task, TaskStatus

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """
    Enumeration of available retry strategies.

    Attributes:
        constant: Fixed delay between retries
        exponential: Exponential backoff (delay = base * 2^attempt)
        exponential_jitter: Exponential backoff with random jitter
            to reduce "thundering herd" problems
    """

    CONSTANT = "constant"
    EXPONENTIAL = "exponential"
    EXPONENTIAL_JITTER = "exponential_jitter"

    def __str__(self) -> str:
        """Return the string representation of the strategy."""
        return self.value


class RetryDecisionReason(Enum):
    """
    Enumeration of reasons for retry decisions.

    These reasons provide insight into why a retry was allowed or denied.
    """

    # Reasons to retry
    WITHIN_MAX_RETRIES = "within_max_retries"
    RETRYABLE_EXCEPTION = "retryable_exception"
    CUSTOM_POLICY_ALLOWED = "custom_policy_allowed"

    # Reasons not to retry
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    NON_RETRYABLE_EXCEPTION = "non_retryable_exception"
    TASK_TERMINAL = "task_terminal"
    CUSTOM_POLICY_DENIED = "custom_policy_denied"

    def __str__(self) -> str:
        """Return the string representation of the reason."""
        return self.value


@dataclass
class RetryDecision:
    """
    Represents a decision about whether to retry a task.

    Attributes:
        should_retry: Whether the task should be retried
        delay: Delay in seconds before retry (if should_retry is True)
        reason: Reason for the decision
        attempt_number: The attempt number (0-indexed)
    """

    should_retry: bool
    delay: float
    reason: RetryDecisionReason
    attempt_number: int

    def __repr__(self) -> str:
        """Return a detailed string representation of the decision."""
        status = "RETRY" if self.should_retry else "NO RETRY"
        return (
            f"RetryDecision({status}, delay={self.delay:.2f}s, "
            f"reason={self.reason.value}, attempt={self.attempt_number})"
        )


@dataclass
class RetryPolicyConfig:
    """
    Configuration for retry policy behavior.

    Attributes:
        max_retries: Maximum number of retry attempts (0 = no retries)
        initial_delay: Initial delay in seconds before first retry
        max_delay: Maximum delay cap in seconds
        strategy: Retry strategy to use
        base_multiplier: Base multiplier for exponential strategies
        jitter_factor: Fraction for jitter (0-1), only for exponential_jitter
        backoff_multiplier: Multiplier for each subsequent attempt (exponential strategies)
    """

    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    base_multiplier: float = 2.0
    jitter_factor: float = 0.1
    backoff_multiplier: float = 2.0

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {self.max_retries}")

        if self.initial_delay < 0:
            raise ValueError(f"initial_delay must be >= 0, got {self.initial_delay}")

        if self.max_delay < 0:
            raise ValueError(f"max_delay must be >= 0, got {self.max_delay}")

        if self.initial_delay > self.max_delay:
            raise ValueError(
                f"initial_delay ({self.initial_delay}) cannot exceed max_delay ({self.max_delay})"
            )

        if self.base_multiplier <= 0:
            raise ValueError(f"base_multiplier must be > 0, got {self.base_multiplier}")

        if not 0 <= self.jitter_factor <= 1:
            raise ValueError(f"jitter_factor must be between 0 and 1, got {self.jitter_factor}")

        if self.backoff_multiplier <= 0:
            raise ValueError(
                f"backoff_multiplier must be > 0, got {self.backoff_multiplier}"
            )


class RetryStrategyCalculator(ABC):
    """
    Abstract base class for retry delay calculation strategies.
    """

    @abstractmethod
    def calculate_delay(self, attempt: int, config: RetryPolicyConfig) -> float:
        """
        Calculate the delay for a given retry attempt.

        Args:
            attempt: Attempt number (0-indexed)
            config: Retry policy configuration

        Returns:
            Delay in seconds
        """
        pass


class ConstantRetryStrategy(RetryStrategyCalculator):
    """
    Constant delay retry strategy.

    Always returns the same delay for all retry attempts.
    """

    def calculate_delay(self, attempt: int, config: RetryPolicyConfig) -> float:
        """
        Calculate constant delay.

        Args:
            attempt: Attempt number (0-indexed)
            config: Retry policy configuration

        Returns:
            Constant delay capped at max_delay
        """
        return min(config.initial_delay, config.max_delay)


class ExponentialRetryStrategy(RetryStrategyCalculator):
    """
    Exponential backoff retry strategy.

    Delay increases exponentially with each attempt:
    delay = initial_delay * (multiplier ^ attempt)
    """

    def calculate_delay(self, attempt: int, config: RetryPolicyConfig) -> float:
        """
        Calculate exponential backoff delay.

        Args:
            attempt: Attempt number (0-indexed)
            config: Retry policy configuration

        Returns:
            Exponentially increasing delay capped at max_delay
        """
        delay = config.initial_delay * (config.backoff_multiplier ** attempt)
        return min(delay, config.max_delay)


class ExponentialJitterRetryStrategy(RetryStrategyCalculator):
    """
    Exponential backoff with jitter retry strategy.

    Adds random jitter to exponential backoff to prevent synchronized
    retry attempts from multiple workers (thundering herd problem).

    Delay = exponential_delay * (1 - jitter_factor + random() * 2 * jitter_factor)
    """

    def calculate_delay(self, attempt: int, config: RetryPolicyConfig) -> float:
        """
        Calculate exponential backoff delay with jitter.

        Args:
            attempt: Attempt number (0-indexed)
            config: Retry policy configuration

        Returns:
            Exponentially increasing delay with random variation, capped at max_delay
        """
        exponential_strategy = ExponentialRetryStrategy()
        base_delay = exponential_strategy.calculate_delay(attempt, config)

        # Add jitter: random value between
        # base_delay * (1 - jitter_factor) and base_delay * (1 + jitter_factor)
        jitter = random.uniform(-config.jitter_factor, config.jitter_factor)
        delayed = base_delay * (1.0 + jitter)

        return max(0, min(delayed, config.max_delay))


class RetryPolicy:
    """
    Comprehensive retry policy for task execution failures.

    This class provides flexible retry mechanisms with multiple strategies,
    exception filtering, and custom retry decision logic.

    Examples:
        >>> # Simple exponential backoff
        >>> policy = RetryPolicy(max_retries=3, strategy=RetryStrategy.EXPONENTIAL)
        >>> decision = policy.should_retry(task, exception)

        >>> # With custom exception handling
        >>> policy = RetryPolicy(
        ...     max_retries=5,
        ...     strategy=RetryStrategy.EXPONENTIAL_JITTER,
        ...     retryable_exceptions=[TimeoutError, ConnectionError],
        ...     non_retryable_exceptions=[ValueError]
        ... )

        >>> # With custom retry function
        >>> def custom_should_retry(task, exception):
        ...     return isinstance(exception, TemporaryError) and task.retry_count < 10
        >>> policy = RetryPolicy(should_retry_func=custom_should_retry)
    """

    # Strategy calculator mapping
    _strategies: dict[RetryStrategy, RetryStrategyCalculator] = {
        RetryStrategy.CONSTANT: ConstantRetryStrategy(),
        RetryStrategy.EXPONENTIAL: ExponentialRetryStrategy(),
        RetryStrategy.EXPONENTIAL_JITTER: ExponentialJitterRetryStrategy(),
    }

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        base_multiplier: float = 2.0,
        jitter_factor: float = 0.1,
        backoff_multiplier: float = 2.0,
        retryable_exceptions: Optional[List[Type[Exception]]] = None,
        non_retryable_exceptions: Optional[List[Type[Exception]]] = None,
        should_retry_func: Optional[Callable[[Task, Exception], bool]] = None,
        config: Optional[RetryPolicyConfig] = None,
    ):
        """
        Initialize a retry policy.

        Args:
            max_retries: Maximum number of retry attempts (0 = no retries)
            initial_delay: Initial delay in seconds before first retry
            max_delay: Maximum delay cap in seconds
            strategy: Retry strategy to use
            base_multiplier: Base multiplier for exponential strategies
            jitter_factor: Fraction for jitter (0-1), only for exponential_jitter
            backoff_multiplier: Multiplier for each subsequent attempt
            retryable_exceptions: Exception types that should trigger retries
                (if None, all exceptions are retryable)
            non_retryable_exceptions: Exception types that should not trigger retries
                (takes precedence over retryable_exceptions)
            should_retry_func: Optional custom function to determine if a task
                should be retried. Signature: should_retry_func(task, exception) -> bool
            config: Optional pre-configured RetryPolicyConfig (overrides other params)

        Raises:
            ValueError: If configuration is invalid
        """
        if config is not None:
            self.config = config
        else:
            self.config = RetryPolicyConfig(
                max_retries=max_retries,
                initial_delay=initial_delay,
                max_delay=max_delay,
                strategy=strategy,
                base_multiplier=base_multiplier,
                jitter_factor=jitter_factor,
                backoff_multiplier=backoff_multiplier,
            )

        # Store exception filters
        self.retryable_exceptions = set(retryable_exceptions or [])
        self.non_retryable_exceptions = set(non_retryable_exceptions or [])

        # Custom retry function
        self.should_retry_func = should_retry_func

        # Get strategy calculator
        self.strategy_calculator = self._strategies[self.config.strategy]

    def get_retry_decision(
        self, task: Task, exception: Exception
    ) -> RetryDecision:
        """
        Get a retry decision for a failed task.

        This method evaluates all policies and returns a comprehensive
        decision including the retry delay and reason.

        Args:
            task: The task that failed
            exception: The exception that caused the failure

        Returns:
            RetryDecision object with retry decision, delay, and reason
        """
        attempt_number = task.retry_count

        # Use custom function if provided
        if self.should_retry_func is not None:
            try:
                custom_decision = self.should_retry_func(task, exception)
                if custom_decision:
                    delay = self._calculate_delay(attempt_number)
                    return RetryDecision(
                        should_retry=True,
                        delay=delay,
                        reason=RetryDecisionReason.CUSTOM_POLICY_ALLOWED,
                        attempt_number=attempt_number,
                    )
                else:
                    return RetryDecision(
                        should_retry=False,
                        delay=0.0,
                        reason=RetryDecisionReason.CUSTOM_POLICY_DENIED,
                        attempt_number=attempt_number,
                    )
            except Exception as e:
                logger.error(
                    f"Custom retry function raised exception: {e}. "
                    f"Falling back to default policy."
                )

        # Check if task is in terminal state
        if task.status in (TaskStatus.COMPLETED,):
            return RetryDecision(
                should_retry=False,
                delay=0.0,
                reason=RetryDecisionReason.TASK_TERMINAL,
                attempt_number=attempt_number,
            )

        # Check max retries
        if attempt_number >= self.config.max_retries:
            return RetryDecision(
                should_retry=False,
                delay=0.0,
                reason=RetryDecisionReason.MAX_RETRIES_EXCEEDED,
                attempt_number=attempt_number,
            )

        # Check exception filters
        retry_allowed = self._check_exception(exception)

        if retry_allowed:
            delay = self._calculate_delay(attempt_number)
            reason = RetryDecisionReason.RETRYABLE_EXCEPTION
            if attempt_number < self.config.max_retries:
                reason = RetryDecisionReason.WITHIN_MAX_RETRIES
            return RetryDecision(
                should_retry=True,
                delay=delay,
                reason=reason,
                attempt_number=attempt_number,
            )
        else:
            return RetryDecision(
                should_retry=False,
                delay=0.0,
                reason=RetryDecisionReason.NON_RETRYABLE_EXCEPTION,
                attempt_number=attempt_number,
            )

    def should_retry(self, task: Task, exception: Exception) -> bool:
        """
        Determine if a task should be retried.

        This is a convenience method that returns only the boolean decision.
        For more detailed information (delay, reason), use get_retry_decision().

        Args:
            task: The task that failed
            exception: The exception that caused the failure

        Returns:
            True if the task should be retried, False otherwise
        """
        decision = self.get_retry_decision(task, exception)
        return decision.should_retry

    def get_retry_delay(self, attempt: int) -> float:
        """
        Get the retry delay for a specific attempt number.

        Args:
            attempt: Attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        return self._calculate_delay(attempt)

    def _calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for a given attempt.

        Args:
            attempt: Attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        return self.strategy_calculator.calculate_delay(attempt, self.config)

    def _check_exception(self, exception: Exception) -> bool:
        """
        Check if an exception should trigger a retry.

        Args:
            exception: The exception to check

        Returns:
            True if the exception should trigger a retry
        """
        # Check non-retryable exceptions first (takes precedence)
        if self.non_retryable_exceptions:
            if any(
                isinstance(exception, exc_type)
                for exc_type in self.non_retryable_exceptions
            ):
                return False

        # If retryable exceptions are specified, check only those
        if self.retryable_exceptions:
            return any(
                isinstance(exception, exc_type) for exc_type in self.retryable_exceptions
            )

        # Default: allow retry for all exceptions
        return True

    def wait_before_retry(self, task: Task, exception: Exception) -> bool:
        """
        Wait the appropriate delay before retrying, if retry is allowed.

        This method blocks the current thread for the calculated delay
        if the task should be retried.

        Args:
            task: The task that failed
            exception: The exception that caused the failure

        Returns:
            True if the task should be retried (after waiting), False otherwise
        """
        decision = self.get_retry_decision(task, exception)

        if not decision.should_retry:
            return False

        logger.debug(
            f"Waiting {decision.delay:.2f}s before retrying task {task.id} "
            f"(attempt {decision.attempt_number}, reason: {decision.reason.value})"
        )
        time.sleep(decision.delay)
        return True

    def get_retry_schedule(self, max_attempts: Optional[int] = None) -> List[Tuple[int, float]]:
        """
        Get the complete retry schedule for debugging/visualization.

        Args:
            max_attempts: Maximum number of attempts to calculate schedule for
                (defaults to max_retries)

        Returns:
            List of (attempt_number, delay) tuples
        """
        if max_attempts is None:
            max_attempts = self.config.max_retries

        schedule = []
        for attempt in range(max_attempts):
            delay = self._calculate_delay(attempt)
            schedule.append((attempt, delay))

        return schedule

    def copy(
        self,
        max_retries: Optional[int] = None,
        initial_delay: Optional[float] = None,
        max_delay: Optional[float] = None,
        strategy: Optional[RetryStrategy] = None,
        retryable_exceptions: Optional[List[Type[Exception]]] = None,
        non_retryable_exceptions: Optional[List[Type[Exception]]] = None,
    ) -> "RetryPolicy":
        """
        Create a copy of the retry policy with optional overrides.

        Args:
            max_retries: Override max retries
            initial_delay: Override initial delay
            max_delay: Override max delay
            strategy: Override retry strategy
            retryable_exceptions: Override retryable exceptions
            non_retryable_exceptions: Override non-retryable exceptions

        Returns:
            New RetryPolicy instance with specified overrides
        """
        # Get current config values
        config = self.config.copy() if hasattr(self.config, "copy") else self.config

        if max_retries is not None:
            config.max_retries = max_retries
        if initial_delay is not None:
            config.initial_delay = initial_delay
        if max_delay is not None:
            config.max_delay = max_delay
        if strategy is not None:
            config.strategy = strategy

        # Copy exception lists
        retryable = retryable_exceptions if retryable_exceptions is not None else list(self.retryable_exceptions)
        non_retryable = non_retryable_exceptions if non_retryable_exceptions is not None else list(self.non_retryable_exceptions)

        return RetryPolicy(
            config=config,
            retryable_exceptions=retryable,
            non_retryable_exceptions=non_retryable,
            should_retry_func=self.should_retry_func,
        )

    def __repr__(self) -> str:
        """Return a detailed string representation of the retry policy."""
        return (
            f"RetryPolicy(strategy={self.config.strategy.value}, "
            f"max_retries={self.config.max_retries}, "
            f"initial_delay={self.config.initial_delay}s, "
            f"max_delay={self.config.max_delay}s)"
        )


# Pre-configured retry policies for common use cases
def simple_retry_policy(max_retries: int = 3) -> RetryPolicy:
    """
    Create a simple exponential backoff retry policy.

    Args:
        max_retries: Maximum number of retry attempts

    Returns:
        RetryPolicy configured for simple exponential backoff
    """
    return RetryPolicy(
        max_retries=max_retries,
        strategy=RetryStrategy.EXPONENTIAL,
        initial_delay=1.0,
        max_delay=60.0,
    )


def aggressive_retry_policy(max_retries: int = 10) -> RetryPolicy:
    """
    Create an aggressive retry policy with many attempts and short delays.

    Suitable for transient failures that resolve quickly.

    Args:
        max_retries: Maximum number of retry attempts

    Returns:
        RetryPolicy configured for aggressive retries
    """
    return RetryPolicy(
        max_retries=max_retries,
        strategy=RetryStrategy.EXPONENTIAL_JITTER,
        initial_delay=0.1,
        max_delay=10.0,
        jitter_factor=0.5,
    )


def conservative_retry_policy(max_retries: int = 3) -> RetryPolicy:
    """
    Create a conservative retry policy with longer delays.

    Suitable for non-critical tasks or overloaded systems.

    Args:
        max_retries: Maximum number of retry attempts

    Returns:
        RetryPolicy configured for conservative retries
    """
    return RetryPolicy(
        max_retries=max_retries,
        strategy=RetryStrategy.EXPONENTIAL,
        initial_delay=5.0,
        max_delay=300.0,
        backoff_multiplier=3.0,
    )


def network_retry_policy() -> RetryPolicy:
    """
    Create a retry policy optimized for network operations.

    Retries common network exceptions with exponential backoff and jitter.

    Returns:
        RetryPolicy configured for network operations
    """
    return RetryPolicy(
        max_retries=5,
        strategy=RetryStrategy.EXPONENTIAL_JITTER,
        initial_delay=1.0,
        max_delay=120.0,
        jitter_factor=0.2,
        retryable_exceptions=[
            ConnectionError,
            TimeoutError,
            OSError,
        ],
    )


def no_retry_policy() -> RetryPolicy:
    """
    Create a policy that never retries.

    Returns:
        RetryPolicy configured with max_retries=0
    """
    return RetryPolicy(max_retries=0)
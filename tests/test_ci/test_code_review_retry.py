import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path('.github/scripts/code_review.py')
spec = importlib.util.spec_from_file_location('code_review_script', MODULE_PATH)
code_review = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(code_review)


class _FakeMessages:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeClient:
    def __init__(self, outcomes):
        self.messages = _FakeMessages(outcomes)


def test_compute_sleep_seconds_backoff_and_jitter_bounds(monkeypatch):
    monkeypatch.setattr(code_review.random, 'uniform', lambda a, b: b)

    # attempt=3 => backoff = min(8, 1 * 2^(3-1)) = 4 ; jitter max=min(0.5, 2)=0.5
    sleep = code_review._compute_sleep_seconds(
        attempt=3,
        base_delay_seconds=1.0,
        max_delay_seconds=8.0,
    )
    assert sleep == pytest.approx(4.5)


def test_retry_until_success_respects_limit(monkeypatch):
    class RetryableError(Exception):
        pass

    monkeypatch.setattr(code_review, '_is_retryable_error', lambda e: isinstance(e, RetryableError))
    monkeypatch.setattr(code_review, '_compute_sleep_seconds', lambda *args, **kwargs: 0)
    monkeypatch.setattr(code_review.time, 'sleep', lambda *_args, **_kwargs: None)

    ok = object()
    client = _FakeClient([RetryableError('t1'), RetryableError('t2'), ok])

    result = code_review.request_review_with_retry(
        client=client,
        diff='x',
        max_attempts=5,
        base_delay_seconds=1,
        max_delay_seconds=8,
    )

    assert result is ok
    assert client.messages.calls == 3


def test_retry_exhaustion_returns_none(monkeypatch):
    """All retryable failures exhausted → returns None (non-blocking)."""
    class RetryableError(Exception):
        pass

    monkeypatch.setattr(code_review, '_is_retryable_error', lambda e: isinstance(e, RetryableError))
    monkeypatch.setattr(code_review, '_compute_sleep_seconds', lambda *args, **kwargs: 0)
    monkeypatch.setattr(code_review.time, 'sleep', lambda *_args, **_kwargs: None)

    client = _FakeClient([RetryableError('a'), RetryableError('b'), RetryableError('c')])

    result = code_review.request_review_with_retry(client=client, diff='x', max_attempts=3)

    assert result is None
    assert client.messages.calls == 3


def test_non_retryable_error_no_retry(monkeypatch):
    monkeypatch.setattr(code_review, '_is_retryable_error', lambda e: False)

    client = _FakeClient([ValueError('bad')])

    with pytest.raises(ValueError):
        code_review.request_review_with_retry(client=client, diff='x', max_attempts=5)

    assert client.messages.calls == 1

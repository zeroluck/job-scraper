"""Invocation-owned completion-attempt budget (including failed attempts)."""
import threading


class RequestBudgetExhausted(RuntimeError):
    """No further provider attempts are authorized for this invocation."""


class RequestBudget:
    def __init__(self, limit: int):
        if limit < 0:
            raise ValueError("request budget must be nonnegative")
        self.limit = limit
        self.used = 0
        self._lock = threading.Lock()

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit

    def consume(self):
        with self._lock:
            if self.exhausted:
                raise RequestBudgetExhausted("request budget exhausted")
            self.used += 1

from collections import deque
from threading import Lock
from time import monotonic, sleep


class RollingTokenBudget:
    def __init__(self, tokens_per_minute: int) -> None:
        self.limit = tokens_per_minute
        self._reservations: deque[tuple[float, int]] = deque()
        self._lock = Lock()

    def reserve(self, token_count: int) -> None:
        if token_count > self.limit:
            raise ValueError(
                f"Estimated request budget ({token_count}) exceeds the configured "
                f"{self.limit}-token per-minute limit."
            )

        while True:
            with self._lock:
                now = monotonic()
                while self._reservations and now - self._reservations[0][0] >= 60:
                    self._reservations.popleft()

                reserved = sum(tokens for _, tokens in self._reservations)
                if reserved + token_count <= self.limit:
                    self._reservations.append((now, token_count))
                    return

                wait_seconds = 60 - (now - self._reservations[0][0]) + 0.1

            sleep(max(wait_seconds, 0.1))

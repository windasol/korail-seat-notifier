"""토큰 버킷 기반 레이트 리미터

에이전트가 코레일 서버에 과부하를 주지 않도록 요청 속도를 제한한다.
비동기 컨텍스트에서 사용하도록 설계.
"""

from __future__ import annotations

import asyncio
from time import monotonic


class TokenBucketRateLimiter:
    """토큰 버킷 레이트 리미터

    Args:
        rate: 초당 허용 요청 수 (기본 1/30 = 30초당 1회)
        burst: 버스트 허용 수 (기본 1)
    """

    __slots__ = ("_rate", "_burst", "_tokens", "_last_refill")

    def __init__(
        self,
        rate: float = 1.0 / 30.0,
        burst: int = 1,
    ) -> None:
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = monotonic()

    def _refill(self) -> None:
        now = monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._burst,
            self._tokens + elapsed * self._rate,
        )
        self._last_refill = now

    async def acquire(self) -> float:
        """토큰 1개 소비. 대기한 시간(초)을 반환."""
        waited = 0.0
        while True:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return waited
            # 다음 토큰까지 대기 시간 계산
            deficit = 1.0 - self._tokens
            sleep_time = deficit / self._rate
            await asyncio.sleep(sleep_time)
            waited += sleep_time

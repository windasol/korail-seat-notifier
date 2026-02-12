"""적응형 폴링 스케줄러 스킬

지수 백오프 + 랜덤 지터로 조회 간격을 동적으로 조정한다.
"""

from __future__ import annotations

import random


class PollerSkill:
    """적응형 폴링 간격 계산"""

    __slots__ = (
        "_base_interval", "_max_interval",
        "_backoff_multiplier", "_jitter_range",
        "_current_interval",
    )

    def __init__(
        self,
        base_interval: float = 30.0,
        max_interval: float = 300.0,
        backoff_multiplier: float = 1.5,
        jitter_range: float = 5.0,
    ) -> None:
        self._base_interval = base_interval
        self._max_interval = max_interval
        self._backoff_multiplier = backoff_multiplier
        self._jitter_range = jitter_range
        self._current_interval = base_interval

    @property
    def current_interval(self) -> float:
        return self._current_interval

    def next_interval(self, had_error: bool) -> float:
        """다음 폴링까지 대기 시간(초) 계산"""
        if had_error:
            self._current_interval = min(
                self._current_interval * self._backoff_multiplier,
                self._max_interval,
            )
        else:
            self._current_interval = max(
                self._current_interval / 1.2,
                self._base_interval,
            )

        jitter = random.uniform(0, self._jitter_range)
        return self._current_interval + jitter

    def reset(self) -> None:
        """간격을 base_interval로 리셋"""
        self._current_interval = self._base_interval

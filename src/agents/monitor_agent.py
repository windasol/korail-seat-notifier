"""모니터링 에이전트 (MonitorAgent)

주기적으로 코레일 좌석 가용성을 조회하고, 좌석 발견 시 이벤트를 발행한다.

상태 머신: IDLE → POLLING → DETECTED → IDLE (루프)
스킬 구성: SeatCheckerSkill + PollerSkill + TokenBucketRateLimiter
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum, auto
from time import monotonic
from typing import Optional

from src.agents.base import BaseAgent
from src.models.config import AgentConfig
from src.models.events import AgentEvent
from src.models.query import CheckResult, TrainQuery
from src.skills.poller import PollerSkill
from src.skills.seat_checker import SeatCheckerSkill
from src.utils.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger("korail.agent.monitor")


class MonitorState(Enum):
    """모니터 에이전트 내부 상태"""
    IDLE = auto()
    POLLING = auto()
    DETECTED = auto()


class MonitorAgent(BaseAgent):
    """좌석 모니터링 에이전트

    적응형 폴링 전략으로 코레일 API를 주기적으로 호출하고
    빈자리 발견 시 orchestrator에게 SEAT_DETECTED 이벤트를 보낸다.
    """

    def __init__(
        self,
        config: AgentConfig,
        event_bus: Optional[asyncio.Queue] = None,  # type: ignore[type-arg]
    ) -> None:
        super().__init__("monitor_agent", event_bus)
        self._config = config
        self._query: Optional[TrainQuery] = None
        self._state = MonitorState.IDLE
        self._request_count = 0
        self._consecutive_errors = 0
        self._start_time = 0.0

        # 스킬 초기화
        self._checker = SeatCheckerSkill(
            request_timeout=config.request_timeout,
            connect_timeout=config.connect_timeout,
            max_connections=config.max_connections,
        )
        self._poller = PollerSkill(
            base_interval=config.base_interval,
            max_interval=config.max_interval,
            backoff_multiplier=config.backoff_multiplier,
            jitter_range=config.jitter_range,
        )
        self._rate_limiter = TokenBucketRateLimiter(
            rate=1.0 / max(config.base_interval, 10.0),
            burst=1,
        )

    @property
    def monitor_state(self) -> MonitorState:
        return self._state

    @property
    def request_count(self) -> int:
        return self._request_count

    @property
    def consecutive_errors(self) -> int:
        return self._consecutive_errors

    def set_query(self, query: TrainQuery) -> None:
        """조회 대상 설정 (Orchestrator가 호출)"""
        self._query = query

    async def setup(self) -> None:
        self._start_time = monotonic()
        logger.info("MonitorAgent 초기화 완료 (간격: %.0fs)", self._config.base_interval)

    async def run(self) -> None:
        """폴링 루프 실행"""
        if self._query is None:
            logger.error("TrainQuery가 설정되지 않았습니다")
            return

        logger.info("모니터링 시작: %s", self._query.summary())

        while not self._stop_event.is_set():
            # 세션 한도 체크
            if not self._check_limits():
                await self.emit(AgentEvent.HEALTH_CRITICAL, "orchestrator", {
                    "reason": "session_limit_reached",
                    "request_count": self._request_count,
                })
                break

            # 레이트 리미터 획득
            await self._rate_limiter.acquire()

            # 폴링 실행
            had_error = await self._poll_once()

            # 다음 간격 계산 & 대기
            interval = self._poller.next_interval(had_error)
            logger.debug("다음 조회까지 %.1f초 대기", interval)

            try:
                await asyncio.wait_for(
                    asyncio.shield(self._stop_event.wait()),
                    timeout=interval,
                )
                # stop_event가 설정됨
                break
            except asyncio.TimeoutError:
                pass  # 정상 대기 완료, 다음 루프

    async def teardown(self) -> None:
        await SeatCheckerSkill.close()
        logger.info("MonitorAgent 정리 완료 (총 %d회 조회)", self._request_count)

    async def _poll_once(self) -> bool:
        """단일 조회 사이클. 에러 발생 시 True 반환."""
        assert self._query is not None

        had_error = False
        self._state = MonitorState.POLLING

        await self.emit(AgentEvent.POLL_START, "orchestrator", {
            "request_count": self._request_count + 1,
        })

        t0 = monotonic()
        try:
            result: CheckResult = await self._checker.check(self._query)
            elapsed_ms = (monotonic() - t0) * 1000
            self._consecutive_errors = 0
            self._request_count += 1

            await self.emit(AgentEvent.POLL_RESULT, "orchestrator", {
                "result": result,
                "elapsed_ms": elapsed_ms,
                "request_count": self._request_count,
            })

            if result.seats_available:
                self._state = MonitorState.DETECTED
                logger.info(
                    "빈자리 발견! %d개 열차 (%.0fms)",
                    len(result.available_trains), elapsed_ms,
                )
                await self.emit(AgentEvent.SEAT_DETECTED, "orchestrator", result)
            else:
                self._state = MonitorState.IDLE
                logger.info(
                    "조회 #%d: 빈자리 없음 (%.0fms)",
                    self._request_count, elapsed_ms,
                )

        except Exception as e:
            had_error = True
            elapsed_ms = (monotonic() - t0) * 1000
            self._consecutive_errors += 1
            self._request_count += 1
            self._state = MonitorState.IDLE

            logger.warning("조회 실패 (%d회 연속): %s", self._consecutive_errors, e)

            if self._consecutive_errors >= self._config.max_consecutive_errors:
                await self.emit(AgentEvent.HEALTH_CRITICAL, "orchestrator", {
                    "reason": "consecutive_errors",
                    "error_count": self._consecutive_errors,
                    "last_error": str(e),
                })

        return had_error

    def _check_limits(self) -> bool:
        """세션 한도 확인. 초과 시 False."""
        elapsed = monotonic() - self._start_time

        if elapsed > self._config.max_session_duration:
            logger.warning("세션 시간 초과 (%.0f분)", elapsed / 60)
            return False
        if self._request_count >= self._config.max_requests_per_session:
            logger.warning("최대 요청 수 초과: %d", self._request_count)
            return False
        return True

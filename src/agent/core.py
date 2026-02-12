"""코레일 좌석 모니터링 에이전트 (메인 오케스트레이터)

Prompt → Agent → Skill 파이프라인의 중심.
상태 머신 기반으로 폴링, 감지, 알림을 순환 실행한다.
"""

from __future__ import annotations

import asyncio
import gc
import logging
import random
from time import monotonic
from typing import Optional

from src.models.config import AgentConfig
from src.models.query import TrainQuery
from src.agent.state import AgentState, validate_transition
from src.agent.metrics import AgentMetrics
from src.skills.seat_checker import SeatCheckerSkill
from src.skills.notifier import NotifierSkill

logger = logging.getLogger("korail.agent")


class KorailAgent:
    """코레일 좌석 모니터링 에이전트"""

    __slots__ = (
        "_state", "_config", "_query", "_current_interval",
        "_request_count", "_error_count", "_start_time",
        "_last_notification_time", "_log_buffer", "_running",
        "_metrics", "_checker", "_notifier",
    )

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        self._config = config or AgentConfig()
        self._state = AgentState.IDLE
        self._query: Optional[TrainQuery] = None
        self._current_interval = self._config.base_interval
        self._request_count = 0
        self._error_count = 0
        self._start_time = 0.0
        self._last_notification_time = 0.0
        self._log_buffer: list[dict] = []
        self._running = False
        self._metrics = AgentMetrics()
        self._checker = SeatCheckerSkill(
            request_timeout=self._config.request_timeout,
            connect_timeout=self._config.connect_timeout,
            max_connections=self._config.max_connections,
        )
        self._notifier = NotifierSkill(
            methods=self._config.notification_methods,
            webhook_url=self._config.webhook_url,
        )

    # ── Properties ──

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def metrics(self) -> AgentMetrics:
        return self._metrics

    @property
    def is_running(self) -> bool:
        return self._running

    # ── State Machine ──

    def _transition(self, new_state: AgentState) -> None:
        old = self._state
        if not validate_transition(old, new_state):
            logger.warning(
                "잘못된 상태 전이 시도: %s → %s", old.name, new_state.name,
            )
            return
        self._state = new_state
        self._log(f"[상태] {old.name} → {new_state.name}")

    # ── Logging (ring buffer) ──

    def _log(self, message: str) -> None:
        entry = {"ts": monotonic() - self._start_time, "msg": message}
        self._log_buffer.append(entry)
        if len(self._log_buffer) > self._config.max_log_entries:
            half = self._config.max_log_entries // 2
            self._log_buffer = self._log_buffer[half:]
        logger.info(message)

    # ── Polling Interval ──

    def _next_interval(self, had_error: bool) -> float:
        if had_error:
            self._current_interval = min(
                self._current_interval * self._config.backoff_multiplier,
                self._config.max_interval,
            )
        else:
            self._current_interval = max(
                self._current_interval / 1.2,
                self._config.base_interval,
            )
        jitter = random.uniform(0, self._config.jitter_range)
        return self._current_interval + jitter

    # ── Resource Guard ──

    def _check_limits(self) -> bool:
        elapsed = monotonic() - self._start_time

        if elapsed > self._config.max_session_duration:
            self._log("세션 시간 초과 (6시간) - 자동 중지")
            return False
        if self._request_count >= self._config.max_requests_per_session:
            self._log(f"최대 요청 수 {self._config.max_requests_per_session} 도달")
            return False
        if self._error_count >= self._config.max_consecutive_errors:
            self._log(f"연속 에러 {self._error_count}회 - 자동 중지")
            return False
        return True

    # ── Main Loop ──

    async def start(self, query: TrainQuery) -> None:
        """모니터링 시작 (blocking coroutine)"""
        self._query = query
        self._start_time = monotonic()
        self._running = True
        self._metrics = AgentMetrics()
        self._transition(AgentState.MONITORING)

        self._log(f"모니터링 시작: {query.summary()}")
        self._log(
            f"설정: 간격={self._config.base_interval}s, "
            f"최대={self._config.max_session_duration/3600:.0f}h, "
            f"알림={','.join(self._config.notification_methods)}"
        )

        try:
            while self._running and self._check_limits():
                had_error = await self._poll_once(query)

                # 주기적 GC & 메트릭 갱신
                if self._request_count % self._config.gc_interval == 0:
                    gc.collect(generation=0)
                    self._metrics.update_memory()

                interval = self._next_interval(had_error)
                self._log(f"다음 조회까지 {interval:.1f}초 대기")

                # sleep을 취소 가능하도록
                try:
                    await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    break
        finally:
            self._transition(AgentState.STOPPED)
            await SeatCheckerSkill.close()
            self._log("에이전트 종료")
            logger.info("\n%s", self._metrics.summary())

    async def _poll_once(self, query: TrainQuery) -> bool:
        """단일 조회 사이클. 에러 발생 시 True 반환."""
        had_error = False
        t0 = monotonic()

        try:
            result = await self._checker.check(query)
            elapsed_ms = (monotonic() - t0) * 1000
            self._metrics.record_request(True, elapsed_ms)
            self._error_count = 0

            if result.seats_available:
                self._transition(AgentState.DETECTED)
                self._metrics.record_detection()
                await self._handle_detection(result)
            else:
                self._log(
                    f"조회 #{self._request_count + 1}: "
                    f"빈 좌석 없음 ({elapsed_ms:.0f}ms)"
                )

        except Exception as e:
            had_error = True
            elapsed_ms = (monotonic() - t0) * 1000
            self._error_count += 1
            self._metrics.record_request(False, elapsed_ms)
            self._transition(AgentState.ERROR)
            self._log(f"에러 ({self._error_count}회): {e}")
            # ERROR에서 MONITORING으로 복귀
            self._transition(AgentState.MONITORING)

        self._request_count += 1
        return had_error

    async def _handle_detection(self, result) -> None:
        """좌석 감지 → 알림 발송"""
        now = monotonic()
        cooldown = self._config.notification_cooldown
        since_last = now - self._last_notification_time

        if since_last < cooldown and self._last_notification_time > 0:
            self._log(
                f"알림 쿨다운 중 (잔여 {cooldown - since_last:.0f}초)"
            )
            self._transition(AgentState.MONITORING)
            return

        available = result.available_trains
        self._log(
            f"빈자리 발견! {len(available)}개 열차:\n"
            + "\n".join(f"    {t.display()}" for t in available[:5])
        )

        try:
            await self._notifier.send(result)
            self._last_notification_time = now
            self._metrics.record_notification()
            self._transition(AgentState.NOTIFIED)
        except Exception as e:
            logger.warning("알림 발송 실패: %s", e)

        self._transition(AgentState.MONITORING)

    def stop(self) -> None:
        """외부에서 모니터링 중지 요청"""
        self._running = False
        self._log("사용자에 의한 수동 중지 요청")

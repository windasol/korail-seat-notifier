"""상태 감시 에이전트 (HealthAgent)

시스템 메트릭 수집, 리소스 한계 감시, 자동 복구 신호 발행.
항상 WATCHING 상태로 활성화되어 있다.

스킬 구성: MetricsSkill (AgentMetrics) + LoggerSkill + GCSkill
"""

from __future__ import annotations

import asyncio
import gc
import logging
from time import monotonic
from typing import Optional

from src.agent.metrics import AgentMetrics
from src.agents.base import BaseAgent
from src.models.config import AgentConfig
from src.models.events import AgentEvent

logger = logging.getLogger("korail.agent.health")

# 상태 보고 주기 (초)
HEALTH_CHECK_INTERVAL = 60.0
# 느린 응답 경고 임계값 (ms)
SLOW_RESPONSE_THRESHOLD_MS = 10_000.0


class HealthAgent(BaseAgent):
    """상태 감시 에이전트 (항상 활성)

    리소스 한계 초과 시:
    - HEALTH_WARNING: 경고 (모니터링 계속)
    - HEALTH_CRITICAL: 세션 중지 요청
    """

    def __init__(
        self,
        config: AgentConfig,
        metrics: AgentMetrics,
        event_bus: Optional[asyncio.Queue] = None,  # type: ignore[type-arg]
    ) -> None:
        super().__init__("health_agent", event_bus)
        self._config = config
        self._metrics = metrics
        self._start_time = 0.0
        self._request_count_ref: Optional[int] = None  # MonitorAgent에서 주입
        self._gc_counter = 0

    @property
    def metrics(self) -> AgentMetrics:
        return self._metrics

    def update_request_count(self, count: int) -> None:
        """MonitorAgent의 요청 수를 동기화 (Orchestrator가 호출)"""
        self._request_count_ref = count

    async def setup(self) -> None:
        self._start_time = monotonic()
        logger.info("HealthAgent 초기화 완료 (메모리 제한: 50MB)")

    async def run(self) -> None:
        """주기적 상태 점검 루프"""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._stop_event.wait()),
                    timeout=HEALTH_CHECK_INTERVAL,
                )
                break  # stop_event 설정됨
            except asyncio.TimeoutError:
                await self._check_health()

    async def teardown(self) -> None:
        gc.collect()  # 세션 종료 시 전체 GC
        logger.info("HealthAgent 정리 완료\n%s", self._metrics.summary())

    async def record_request(self, success: bool, elapsed_ms: float) -> None:
        """요청 결과 기록 (MonitorAgent가 직접 호출 대신 Orchestrator 경유)"""
        self._metrics.record_request(success, elapsed_ms)
        self._gc_counter += 1

        # GCSkill: 50회마다 가비지 컬렉션
        if self._gc_counter >= self._config.gc_interval:
            gc.collect(generation=0)
            self._gc_counter = 0
            logger.debug("GC 실행 (generation 0)")

        # 메모리 갱신
        self._metrics.update_memory()

        # 느린 응답 경고
        if elapsed_ms > SLOW_RESPONSE_THRESHOLD_MS:
            logger.warning("느린 응답 감지: %.0fms", elapsed_ms)
            await self.emit(AgentEvent.HEALTH_WARNING, "orchestrator", {
                "reason": "slow_response",
                "elapsed_ms": elapsed_ms,
            })

        # 메모리 경고
        if self._metrics.peak_memory_mb > 45.0:  # 50MB 임박 전 경고
            logger.warning("메모리 사용량 높음: %.1fMB", self._metrics.peak_memory_mb)
            await self.emit(AgentEvent.HEALTH_WARNING, "orchestrator", {
                "reason": "high_memory",
                "memory_mb": self._metrics.peak_memory_mb,
            })

    def record_detection(self) -> None:
        self._metrics.record_detection()

    def record_notification(self) -> None:
        self._metrics.record_notification()

    async def _check_health(self) -> None:
        """주기적 상태 점검"""
        elapsed = monotonic() - self._start_time
        self._metrics.update_memory()

        logger.info(
            "상태 점검: %.0f분 경과, %d회 요청, 메모리 %.1fMB",
            elapsed / 60,
            self._metrics.total_requests,
            self._metrics.peak_memory_mb,
        )

        # 세션 시간 초과 체크
        if elapsed > self._config.max_session_duration:
            logger.warning("세션 시간 초과 → 중지 신호 발행")
            await self.emit(AgentEvent.HEALTH_CRITICAL, "orchestrator", {
                "reason": "session_timeout",
                "elapsed_s": elapsed,
            })
            return

        # 메모리 50MB 초과 체크
        if self._metrics.peak_memory_mb > 50.0:
            logger.warning("메모리 한계 초과: %.1fMB", self._metrics.peak_memory_mb)
            await self.emit(AgentEvent.HEALTH_CRITICAL, "orchestrator", {
                "reason": "memory_limit",
                "memory_mb": self._metrics.peak_memory_mb,
            })

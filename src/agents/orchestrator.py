"""오케스트레이터 에이전트 (OrchestratorAgent)

전체 파이프라인을 제어한다:
  InputAgent → MonitorAgent → NotifierAgent
  HealthAgent (상시 감시)

이벤트 기반 통신:
  - 중앙 event_bus (asyncio.Queue) 통해 모든 에이전트 메시지 수신
  - SEAT_DETECTED → NotifierAgent 위임
  - HEALTH_CRITICAL / SESSION_STOP → 전체 에이전트 종료

라이프사이클: IDLE → RUNNING → STOPPING → STOPPED
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum, auto
from time import monotonic
from typing import Optional

from src.agent.metrics import AgentMetrics
from src.agents.health_agent import HealthAgent
from src.agents.input_agent import InputAgent
from src.agents.monitor_agent import MonitorAgent
from src.agents.notifier_agent import NotifierAgent
from src.models.config import AgentConfig
from src.models.events import AgentEvent, AgentMessage
from src.models.query import CheckResult, TrainQuery

logger = logging.getLogger("korail.agent.orchestrator")


class OrchestratorState(Enum):
    IDLE = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()


class OrchestratorAgent:
    """멀티 에이전트 파이프라인 총괄 오케스트레이터

    단일 세션 = 단일 OrchestratorAgent 인스턴스.
    모든 에이전트 간 통신은 Orchestrator를 경유한다.
    """

    GRACEFUL_SHUTDOWN_TIMEOUT = 10.0  # 초

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        self._config = config or AgentConfig()
        self._state = OrchestratorState.IDLE
        self._metrics = AgentMetrics()

        # 중앙 이벤트 버스
        self._event_bus: asyncio.Queue[AgentMessage] = asyncio.Queue()

        # 서브 에이전트 생성
        self._input_agent = InputAgent(event_bus=self._event_bus)
        self._monitor_agent = MonitorAgent(
            config=self._config,
            event_bus=self._event_bus,
        )
        self._notifier_agent = NotifierAgent(
            config=self._config,
            event_bus=self._event_bus,
        )
        self._health_agent = HealthAgent(
            config=self._config,
            metrics=self._metrics,
            event_bus=self._event_bus,
        )

        self._tasks: list[asyncio.Task] = []  # type: ignore[type-arg]

    @property
    def state(self) -> OrchestratorState:
        return self._state

    @property
    def metrics(self) -> AgentMetrics:
        return self._metrics

    def stop(self) -> None:
        """외부에서 안전 종료 요청 (Ctrl+C 등)"""
        if self._state == OrchestratorState.RUNNING:
            logger.info("종료 요청 수신")
            self._state = OrchestratorState.STOPPING
            self._monitor_agent.request_stop()
            self._notifier_agent.request_stop()
            self._health_agent.request_stop()

    async def run(self, query: TrainQuery) -> AgentMetrics:
        """전체 파이프라인 실행 (blocking)

        Returns:
            AgentMetrics: 세션 종료 후 메트릭 요약
        """
        self._state = OrchestratorState.RUNNING
        start_time = monotonic()

        logger.info("오케스트레이터 시작: %s", query.summary())
        logger.info(
            "설정: 간격=%.0fs, 세션 최대=%gh, 알림=%s",
            self._config.base_interval,
            self._config.max_session_duration / 3600,
            ",".join(self._config.notification_methods),
        )

        # InputAgent를 통해 쿼리 검증 및 전달
        await self._input_agent.setup()
        validated_query = await self._input_agent.process_query(query)
        await self._input_agent.teardown()

        # MonitorAgent에 쿼리 설정
        self._monitor_agent.set_query(validated_query)

        try:
            # 서브 에이전트 태스크 시작
            monitor_task = asyncio.create_task(
                self._monitor_agent.start(),
                name="monitor_agent",
            )
            notifier_task = asyncio.create_task(
                self._notifier_agent.start(),
                name="notifier_agent",
            )
            health_task = asyncio.create_task(
                self._health_agent.start(),
                name="health_agent",
            )
            self._tasks = [monitor_task, notifier_task, health_task]

            # 이벤트 버스 처리 루프
            await self._event_loop(monitor_task)

        finally:
            await self._shutdown()
            elapsed = monotonic() - start_time
            logger.info("오케스트레이터 종료 (%.1f분 경과)", elapsed / 60)
            self._state = OrchestratorState.STOPPED

        return self._metrics

    async def _event_loop(self, monitor_task: asyncio.Task) -> None:  # type: ignore[type-arg]
        """중앙 이벤트 처리 루프"""
        while self._state == OrchestratorState.RUNNING:
            # MonitorAgent가 종료되면 세션 종료
            if monitor_task.done():
                logger.info("MonitorAgent 종료 → 세션 종료")
                break

            try:
                msg = await asyncio.wait_for(
                    self._event_bus.get(),
                    timeout=1.0,
                )
                await self._dispatch(msg)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def _dispatch(self, msg: AgentMessage) -> None:
        """이벤트 타입별 라우팅"""
        event = msg.event
        logger.debug("이벤트 수신: %s from %s", event, msg.source)

        if event == AgentEvent.POLL_RESULT:
            # 요청 메트릭 기록
            payload = msg.payload
            if isinstance(payload, dict):
                success = True
                elapsed_ms = payload.get("elapsed_ms", 0.0)
                await self._health_agent.record_request(success, elapsed_ms)

        elif event == AgentEvent.SEAT_DETECTED:
            # 좌석 감지 → Notifier에게 위임
            if isinstance(msg.payload, CheckResult):
                self._health_agent.record_detection()
                await self._notifier_agent.notify(msg.payload)

        elif event == AgentEvent.NOTIFY_COMPLETE:
            # 알림 완료 기록
            self._health_agent.record_notification()
            payload = msg.payload
            if isinstance(payload, dict):
                logger.info(
                    "알림 완료: %d개 열차, 누적 %d회",
                    payload.get("trains_count", 0),
                    payload.get("notification_number", 0),
                )

        elif event == AgentEvent.HEALTH_WARNING:
            # 경고 로그만 (모니터링 계속)
            payload = msg.payload
            if isinstance(payload, dict):
                logger.warning("상태 경고: %s", payload.get("reason", "unknown"))

        elif event == AgentEvent.HEALTH_CRITICAL:
            # 임계 상태 → 세션 종료
            payload = msg.payload
            if isinstance(payload, dict):
                reason = payload.get("reason", "unknown")
                logger.error("임계 상태 → 세션 종료: %s", reason)
            self.stop()

        elif event == AgentEvent.SESSION_STOP:
            # 명시적 세션 종료 신호
            logger.info("SESSION_STOP 수신 → 세션 종료")
            self.stop()

    async def _shutdown(self) -> None:
        """Graceful shutdown: 모든 에이전트 종료 대기"""
        self._state = OrchestratorState.STOPPING

        # 모든 에이전트에 종료 신호
        self._monitor_agent.request_stop()
        self._notifier_agent.request_stop()
        self._health_agent.request_stop()

        if not self._tasks:
            return

        # 종료 완료까지 대기 (타임아웃)
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._tasks, return_exceptions=True),
                timeout=self.GRACEFUL_SHUTDOWN_TIMEOUT,
            )
            logger.debug("모든 에이전트 정상 종료")
        except asyncio.TimeoutError:
            logger.warning("강제 종료 (%.0fs 타임아웃)", self.GRACEFUL_SHUTDOWN_TIMEOUT)
            for task in self._tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)

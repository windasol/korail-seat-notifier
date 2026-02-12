"""통합 테스트: 모니터링 플로우

MonitorAgent → 이벤트 버스 → Orchestrator 흐름을 검증한다.
실제 HTTP 호출은 Mock으로 대체한다.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.monitor_agent import MonitorAgent, MonitorState
from src.models.config import AgentConfig
from src.models.events import AgentEvent
from src.models.query import TrainQuery


@pytest.fixture
def fast_config() -> AgentConfig:
    return AgentConfig(
        base_interval=0.05,
        max_interval=0.2,
        max_session_duration=2.0,
        max_requests_per_session=2,
        max_consecutive_errors=2,
        jitter_range=0.0,
    )


class TestMonitorFlow:
    """MonitorAgent → 이벤트 버스 통합 테스트"""

    @pytest.mark.asyncio
    async def test_seat_detected_event_emitted(
        self,
        fast_config: AgentConfig,
        sample_query: TrainQuery,
        check_result_with_seats,
    ) -> None:
        """좌석 발견 시 SEAT_DETECTED 이벤트가 버스에 전달되어야 한다"""
        bus: asyncio.Queue = asyncio.Queue()
        agent = MonitorAgent(fast_config, event_bus=bus)
        agent.set_query(sample_query)

        with patch.object(
            agent._checker, "check", new_callable=AsyncMock,
            return_value=check_result_with_seats,
        ):
            # 2회 요청 후 자동 종료 (max_requests_per_session=2)
            await agent.start()

        # 이벤트 버스에서 SEAT_DETECTED 확인
        events = []
        while not bus.empty():
            events.append((await bus.get()).event)

        assert AgentEvent.SEAT_DETECTED in events

    @pytest.mark.asyncio
    async def test_error_backoff_flow(
        self,
        fast_config: AgentConfig,
        sample_query: TrainQuery,
    ) -> None:
        """연속 오류 시 HEALTH_CRITICAL 이벤트가 발행되어야 한다"""
        bus: asyncio.Queue = asyncio.Queue()
        agent = MonitorAgent(fast_config, event_bus=bus)
        agent.set_query(sample_query)

        error_count = [0]

        async def failing_check(query: TrainQuery):  # type: ignore[return]
            error_count[0] += 1
            raise ConnectionError("서버 응답 없음")

        with patch.object(agent._checker, "check", side_effect=failing_check):
            await agent.start()

        events = []
        while not bus.empty():
            events.append((await bus.get()).event)

        assert AgentEvent.HEALTH_CRITICAL in events

    @pytest.mark.asyncio
    async def test_no_seat_no_detection_event(
        self,
        fast_config: AgentConfig,
        sample_query: TrainQuery,
        check_result_no_seats,
    ) -> None:
        """빈자리 없을 때 SEAT_DETECTED 이벤트 미발행"""
        bus: asyncio.Queue = asyncio.Queue()
        agent = MonitorAgent(fast_config, event_bus=bus)
        agent.set_query(sample_query)

        with patch.object(
            agent._checker, "check", new_callable=AsyncMock,
            return_value=check_result_no_seats,
        ):
            await agent.start()

        events = []
        while not bus.empty():
            events.append((await bus.get()).event)

        assert AgentEvent.SEAT_DETECTED not in events

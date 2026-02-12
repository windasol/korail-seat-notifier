"""MonitorAgent 단위 테스트"""

from __future__ import annotations

import asyncio
from datetime import date, time
from time import monotonic
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.monitor_agent import MonitorAgent, MonitorState
from src.models.config import AgentConfig
from src.models.events import AgentEvent
from src.models.query import CheckResult, TrainInfo, TrainQuery


@pytest.fixture
def fast_config() -> AgentConfig:
    return AgentConfig(
        base_interval=0.1,
        max_interval=0.5,
        max_session_duration=5.0,
        max_requests_per_session=3,
        max_consecutive_errors=2,
    )


class TestMonitorAgentInit:
    def test_initial_state(self, fast_config: AgentConfig) -> None:
        agent = MonitorAgent(fast_config)
        assert agent.monitor_state == MonitorState.IDLE
        assert agent.request_count == 0
        assert agent.consecutive_errors == 0

    def test_set_query(
        self, fast_config: AgentConfig, sample_query: TrainQuery
    ) -> None:
        agent = MonitorAgent(fast_config)
        agent.set_query(sample_query)
        assert agent._query == sample_query


class TestMonitorAgentPollOnce:
    """단일 폴링 사이클 테스트"""

    @pytest.mark.asyncio
    async def test_poll_success_no_seats(
        self,
        fast_config: AgentConfig,
        sample_query: TrainQuery,
        check_result_no_seats: CheckResult,
    ) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        agent = MonitorAgent(fast_config, event_bus=bus)
        agent.set_query(sample_query)
        await agent.setup()

        with patch.object(agent._checker, "check", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = check_result_no_seats
            had_error = await agent._poll_once()

        assert not had_error
        assert agent.request_count == 1
        assert agent.consecutive_errors == 0
        assert agent.monitor_state == MonitorState.IDLE

    @pytest.mark.asyncio
    async def test_poll_success_with_seats_emits_event(
        self,
        fast_config: AgentConfig,
        sample_query: TrainQuery,
        check_result_with_seats: CheckResult,
    ) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        agent = MonitorAgent(fast_config, event_bus=bus)
        agent.set_query(sample_query)
        await agent.setup()

        with patch.object(agent._checker, "check", new_callable=AsyncMock) as mock_check:
            mock_check.return_value = check_result_with_seats
            had_error = await agent._poll_once()

        assert not had_error
        assert agent.monitor_state == MonitorState.DETECTED

        # SEAT_DETECTED 이벤트 확인
        events = []
        while not bus.empty():
            events.append((await bus.get()).event)

        assert AgentEvent.SEAT_DETECTED in events

    @pytest.mark.asyncio
    async def test_poll_error_increments_counter(
        self,
        fast_config: AgentConfig,
        sample_query: TrainQuery,
    ) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        agent = MonitorAgent(fast_config, event_bus=bus)
        agent.set_query(sample_query)
        await agent.setup()

        with patch.object(
            agent._checker, "check", new_callable=AsyncMock,
            side_effect=Exception("네트워크 오류"),
        ):
            had_error = await agent._poll_once()

        assert had_error
        assert agent.consecutive_errors == 1

    @pytest.mark.asyncio
    async def test_critical_event_on_max_errors(
        self,
        fast_config: AgentConfig,
        sample_query: TrainQuery,
    ) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        agent = MonitorAgent(fast_config, event_bus=bus)
        agent.set_query(sample_query)
        agent._consecutive_errors = fast_config.max_consecutive_errors - 1
        await agent.setup()

        with patch.object(
            agent._checker, "check", new_callable=AsyncMock,
            side_effect=Exception("오류"),
        ):
            await agent._poll_once()

        events = []
        while not bus.empty():
            events.append((await bus.get()).event)

        assert AgentEvent.HEALTH_CRITICAL in events


class TestMonitorAgentLimits:
    def test_check_limits_normal(self, fast_config: AgentConfig) -> None:
        agent = MonitorAgent(fast_config)
        agent._start_time = monotonic()
        assert agent._check_limits() is True

    def test_check_limits_max_requests(self, fast_config: AgentConfig) -> None:
        agent = MonitorAgent(fast_config)
        agent._start_time = monotonic()
        agent._request_count = fast_config.max_requests_per_session
        assert agent._check_limits() is False

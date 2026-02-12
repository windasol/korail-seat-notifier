"""OrchestratorAgent 단위 테스트"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.orchestrator import OrchestratorAgent, OrchestratorState
from src.models.config import AgentConfig
from src.models.events import AgentEvent, AgentMessage
from src.models.query import TrainQuery


@pytest.fixture
def fast_config() -> AgentConfig:
    return AgentConfig(
        base_interval=0.1,
        max_interval=0.3,
        max_session_duration=2.0,
        max_requests_per_session=3,
        notification_cooldown=0.05,
        notification_methods=[],  # 테스트에서 실제 알림 없음
    )


class TestOrchestratorInit:
    def test_initial_state(self, fast_config: AgentConfig) -> None:
        orch = OrchestratorAgent(fast_config)
        assert orch.state == OrchestratorState.IDLE

    def test_default_config(self) -> None:
        orch = OrchestratorAgent()
        assert orch._config is not None


class TestOrchestratorStop:
    def test_stop_changes_state(self, fast_config: AgentConfig) -> None:
        orch = OrchestratorAgent(fast_config)
        orch._state = OrchestratorState.RUNNING
        orch.stop()
        assert orch.state == OrchestratorState.STOPPING

    def test_stop_when_not_running_is_noop(self, fast_config: AgentConfig) -> None:
        orch = OrchestratorAgent(fast_config)
        # IDLE 상태에서는 아무것도 하지 않음
        orch.stop()
        assert orch.state == OrchestratorState.IDLE


class TestOrchestratorDispatch:
    """이벤트 디스패치 테스트"""

    @pytest.mark.asyncio
    async def test_dispatch_seat_detected(
        self,
        fast_config: AgentConfig,
        check_result_with_seats,
    ) -> None:
        orch = OrchestratorAgent(fast_config)
        orch._state = OrchestratorState.RUNNING

        msg = AgentMessage(
            event=AgentEvent.SEAT_DETECTED,
            source="monitor_agent",
            target="orchestrator",
            payload=check_result_with_seats,
        )

        with patch.object(
            orch._notifier_agent, "notify", new_callable=AsyncMock
        ) as mock_notify:
            await orch._dispatch(msg)

        mock_notify.assert_called_once_with(check_result_with_seats)

    @pytest.mark.asyncio
    async def test_dispatch_health_critical_stops(
        self, fast_config: AgentConfig
    ) -> None:
        orch = OrchestratorAgent(fast_config)
        orch._state = OrchestratorState.RUNNING

        msg = AgentMessage(
            event=AgentEvent.HEALTH_CRITICAL,
            source="monitor_agent",
            target="orchestrator",
            payload={"reason": "session_limit_reached"},
        )

        await orch._dispatch(msg)

        assert orch.state == OrchestratorState.STOPPING

    @pytest.mark.asyncio
    async def test_dispatch_session_stop(self, fast_config: AgentConfig) -> None:
        orch = OrchestratorAgent(fast_config)
        orch._state = OrchestratorState.RUNNING

        msg = AgentMessage(
            event=AgentEvent.SESSION_STOP,
            source="orchestrator",
            target="*",
            payload=None,
        )

        await orch._dispatch(msg)
        assert orch.state == OrchestratorState.STOPPING

    @pytest.mark.asyncio
    async def test_dispatch_poll_result_records_metrics(
        self, fast_config: AgentConfig
    ) -> None:
        orch = OrchestratorAgent(fast_config)
        orch._state = OrchestratorState.RUNNING

        msg = AgentMessage(
            event=AgentEvent.POLL_RESULT,
            source="monitor_agent",
            target="orchestrator",
            payload={"elapsed_ms": 500.0, "request_count": 1},
        )

        with patch.object(
            orch._health_agent, "record_request", new_callable=AsyncMock
        ) as mock_record:
            await orch._dispatch(msg)

        mock_record.assert_called_once_with(True, 500.0)


class TestOrchestratorRun:
    """전체 실행 플로우 테스트 (단순 Mock)"""

    @pytest.mark.asyncio
    async def test_run_stops_when_monitor_done(
        self,
        fast_config: AgentConfig,
        sample_query: TrainQuery,
    ) -> None:
        orch = OrchestratorAgent(fast_config)

        # MonitorAgent가 즉시 종료되도록 mock
        async def instant_monitor_start() -> None:
            return

        with (
            patch.object(orch._monitor_agent, "start", side_effect=instant_monitor_start),
            patch.object(orch._notifier_agent, "start", new_callable=AsyncMock),
            patch.object(orch._health_agent, "start", new_callable=AsyncMock),
        ):
            metrics = await orch.run(sample_query)

        assert orch.state == OrchestratorState.STOPPED
        assert metrics is not None

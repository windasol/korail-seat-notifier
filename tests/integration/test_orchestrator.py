"""통합 테스트: OrchestratorAgent 전체 파이프라인

Input → Monitor → Notifier → Health 흐름을 검증한다.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.orchestrator import OrchestratorAgent, OrchestratorState
from src.models.config import AgentConfig
from src.models.query import TrainQuery


@pytest.fixture
def integration_config() -> AgentConfig:
    return AgentConfig(
        base_interval=0.05,
        max_interval=0.2,
        max_session_duration=3.0,
        max_requests_per_session=3,
        max_consecutive_errors=2,
        notification_cooldown=0.01,
        notification_methods=[],  # 실제 OS 알림 비활성화
        jitter_range=0.0,
    )


class TestOrchestratorIntegration:
    @pytest.mark.asyncio
    async def test_pipeline_runs_and_stops(
        self,
        integration_config: AgentConfig,
        sample_query: TrainQuery,
        check_result_no_seats,
    ) -> None:
        """전체 파이프라인: 3회 조회 후 max_requests 도달 → 자동 종료"""
        orch = OrchestratorAgent(integration_config)

        with patch.object(
            orch._monitor_agent._checker, "check",
            new_callable=AsyncMock,
            return_value=check_result_no_seats,
        ):
            metrics = await orch.run(sample_query)

        assert orch.state == OrchestratorState.STOPPED
        assert metrics.total_requests <= integration_config.max_requests_per_session + 1

    @pytest.mark.asyncio
    async def test_seat_detection_triggers_notification(
        self,
        integration_config: AgentConfig,
        sample_query: TrainQuery,
        check_result_with_seats,
    ) -> None:
        """좌석 감지 시 NotifierAgent로 알림이 전달되어야 한다"""
        orch = OrchestratorAgent(integration_config)

        notified_results = []

        original_notify = orch._notifier_agent.notify

        async def capture_notify(result):  # type: ignore[return]
            notified_results.append(result)

        orch._notifier_agent.notify = capture_notify  # type: ignore[method-assign]

        with patch.object(
            orch._monitor_agent._checker, "check",
            new_callable=AsyncMock,
            return_value=check_result_with_seats,
        ):
            await orch.run(sample_query)

        assert len(notified_results) > 0

    @pytest.mark.asyncio
    async def test_stop_graceful_shutdown(
        self,
        integration_config: AgentConfig,
        sample_query: TrainQuery,
        check_result_no_seats,
    ) -> None:
        """stop() 호출 시 Graceful Shutdown이 완료되어야 한다"""
        orch = OrchestratorAgent(integration_config)

        async def check_then_stop(query):  # type: ignore[return]
            # 1회 조회 후 orchestrator를 외부에서 중지
            orch.stop()
            return check_result_no_seats

        with patch.object(
            orch._monitor_agent._checker, "check",
            side_effect=check_then_stop,
        ):
            metrics = await orch.run(sample_query)

        assert orch.state == OrchestratorState.STOPPED

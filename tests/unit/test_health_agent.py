"""HealthAgent 단위 테스트"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from src.agent.metrics import AgentMetrics
from src.agents.health_agent import HealthAgent
from src.models.config import AgentConfig
from src.models.events import AgentEvent


@pytest.fixture
def health_config() -> AgentConfig:
    return AgentConfig(
        max_session_duration=5.0,
        max_consecutive_errors=3,
        gc_interval=5,
    )


class TestHealthAgentMetrics:
    """메트릭 기록 테스트"""

    @pytest.mark.asyncio
    async def test_record_request_success(self, health_config: AgentConfig) -> None:
        metrics = AgentMetrics()
        agent = HealthAgent(health_config, metrics)

        await agent.record_request(success=True, elapsed_ms=500.0)

        assert metrics.total_requests == 1
        assert metrics.successful_checks == 1
        assert metrics.failed_checks == 0

    @pytest.mark.asyncio
    async def test_record_request_failure(self, health_config: AgentConfig) -> None:
        metrics = AgentMetrics()
        agent = HealthAgent(health_config, metrics)

        await agent.record_request(success=False, elapsed_ms=1000.0)

        assert metrics.total_requests == 1
        assert metrics.failed_checks == 1

    def test_record_detection(self, health_config: AgentConfig) -> None:
        metrics = AgentMetrics()
        agent = HealthAgent(health_config, metrics)

        agent.record_detection()
        assert metrics.seats_detected_count == 1

    def test_record_notification(self, health_config: AgentConfig) -> None:
        metrics = AgentMetrics()
        agent = HealthAgent(health_config, metrics)

        agent.record_notification()
        assert metrics.notifications_sent == 1


class TestHealthAgentGC:
    """GC 트리거 테스트"""

    @pytest.mark.asyncio
    async def test_gc_triggered_at_interval(self, health_config: AgentConfig) -> None:
        metrics = AgentMetrics()
        bus: asyncio.Queue = asyncio.Queue()
        agent = HealthAgent(health_config, metrics, event_bus=bus)

        import gc
        with patch("gc.collect") as mock_gc:
            # gc_interval(5)회만큼 요청 기록
            for _ in range(health_config.gc_interval):
                await agent.record_request(success=True, elapsed_ms=100.0)

            mock_gc.assert_called()


class TestHealthAgentWarnings:
    """경고 이벤트 테스트"""

    @pytest.mark.asyncio
    async def test_slow_response_emits_warning(self, health_config: AgentConfig) -> None:
        metrics = AgentMetrics()
        bus: asyncio.Queue = asyncio.Queue()
        agent = HealthAgent(health_config, metrics, event_bus=bus)

        # 10초 초과 응답 → 경고
        await agent.record_request(success=True, elapsed_ms=15_000.0)

        events = []
        while not bus.empty():
            events.append((await bus.get()).event)

        assert AgentEvent.HEALTH_WARNING in events

    @pytest.mark.asyncio
    async def test_setup_and_teardown(self, health_config: AgentConfig) -> None:
        metrics = AgentMetrics()
        agent = HealthAgent(health_config, metrics)

        await agent.setup()
        await agent.teardown()

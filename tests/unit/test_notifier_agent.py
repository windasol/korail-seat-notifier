"""NotifierAgent 단위 테스트"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.notifier_agent import NotifierAgent
from src.models.config import AgentConfig
from src.models.events import AgentEvent
from src.models.query import CheckResult
from src.skills.notifier import NotifierSkill


@pytest.fixture
def notifier_config() -> AgentConfig:
    return AgentConfig(
        notification_cooldown=0.05,  # 50ms 테스트용
        notification_methods=["desktop"],
    )


def make_mock_notifier() -> MagicMock:
    """NotifierSkill을 MagicMock으로 대체 (slots 우회)"""
    mock = MagicMock(spec=NotifierSkill)
    mock.send = AsyncMock()
    return mock


class TestNotifierAgentCooldown:
    """쿨다운 동작 테스트"""

    @pytest.mark.asyncio
    async def test_first_notification_sent(
        self,
        notifier_config: AgentConfig,
        check_result_with_seats: CheckResult,
    ) -> None:
        mock_notifier = make_mock_notifier()
        agent = NotifierAgent(notifier_config, notifier=mock_notifier)

        await agent._handle_notification(check_result_with_seats)

        mock_notifier.send.assert_called_once()
        assert agent.notifications_sent == 1

    @pytest.mark.asyncio
    async def test_second_notification_within_cooldown_skipped(
        self,
        notifier_config: AgentConfig,
        check_result_with_seats: CheckResult,
    ) -> None:
        mock_notifier = make_mock_notifier()
        agent = NotifierAgent(notifier_config, notifier=mock_notifier)

        await agent._handle_notification(check_result_with_seats)
        await agent._handle_notification(check_result_with_seats)  # 쿨다운 중

        assert mock_notifier.send.call_count == 1  # 두 번째는 스킵

    @pytest.mark.asyncio
    async def test_notification_after_cooldown_sent(
        self,
        notifier_config: AgentConfig,
        check_result_with_seats: CheckResult,
    ) -> None:
        mock_notifier = make_mock_notifier()
        agent = NotifierAgent(notifier_config, notifier=mock_notifier)

        await agent._handle_notification(check_result_with_seats)
        # 쿨다운 대기
        await asyncio.sleep(notifier_config.notification_cooldown + 0.05)
        await agent._handle_notification(check_result_with_seats)

        assert mock_notifier.send.call_count == 2

    @pytest.mark.asyncio
    async def test_no_notification_when_no_seats(
        self,
        notifier_config: AgentConfig,
        check_result_no_seats: CheckResult,
    ) -> None:
        mock_notifier = make_mock_notifier()
        agent = NotifierAgent(notifier_config, notifier=mock_notifier)

        await agent._handle_notification(check_result_no_seats)

        mock_notifier.send.assert_not_called()
        assert agent.notifications_sent == 0


class TestNotifierAgentEventEmission:
    """이벤트 발행 테스트"""

    @pytest.mark.asyncio
    async def test_emits_notify_complete_event(
        self,
        notifier_config: AgentConfig,
        check_result_with_seats: CheckResult,
    ) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        mock_notifier = make_mock_notifier()
        agent = NotifierAgent(notifier_config, event_bus=bus, notifier=mock_notifier)

        await agent._handle_notification(check_result_with_seats)

        events = []
        while not bus.empty():
            events.append((await bus.get()).event)

        assert AgentEvent.NOTIFY_COMPLETE in events


class TestNotifierAgentInbox:
    """inbox 큐 동작 테스트"""

    @pytest.mark.asyncio
    async def test_notify_puts_to_inbox(
        self,
        notifier_config: AgentConfig,
        check_result_with_seats: CheckResult,
    ) -> None:
        agent = NotifierAgent(notifier_config)
        await agent.notify(check_result_with_seats)
        assert not agent.inbox.empty()
        result = await agent.inbox.get()
        assert result == check_result_with_seats

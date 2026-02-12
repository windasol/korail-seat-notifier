"""알림 스킬 테스트"""

import pytest
from datetime import time
from unittest.mock import AsyncMock, patch

from src.models.query import TrainInfo, CheckResult
from src.skills.notifier import NotifierSkill, NotificationPayload


def _make_result(seats: int = 5) -> CheckResult:
    trains = (
        TrainInfo("101", "KTX", time(9, 0), time(11, 30), seats, 0, 150),
    )
    return CheckResult(
        query_timestamp=0.0,
        trains=trains,
        seats_available=seats > 0,
        raw_response_size=512,
    )


class TestNotifierSkill:
    @pytest.mark.asyncio
    async def test_no_notification_when_no_seats(self):
        result = _make_result(seats=0)
        notifier = NotifierSkill(methods=["desktop"])
        # send() should return without doing anything
        await notifier.send(result)

    @pytest.mark.asyncio
    async def test_sound_method_registered(self):
        notifier = NotifierSkill(methods=["sound"])
        result = _make_result(seats=3)
        with patch.object(
            NotifierSkill, "_sound_notify", new_callable=AsyncMock
        ) as mock_sound:
            await notifier.send(result)
            mock_sound.assert_called_once()

    @pytest.mark.asyncio
    async def test_desktop_method_registered(self):
        notifier = NotifierSkill(methods=["desktop"])
        result = _make_result(seats=3)
        with patch.object(
            NotifierSkill, "_desktop_notify", new_callable=AsyncMock
        ) as mock_desktop:
            await notifier.send(result)
            mock_desktop.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_skipped_without_url(self):
        notifier = NotifierSkill(methods=["webhook"], webhook_url="")
        result = _make_result(seats=3)
        # No exception, webhook silently skipped
        await notifier.send(result)

    @pytest.mark.asyncio
    async def test_multiple_methods(self):
        notifier = NotifierSkill(methods=["desktop", "sound"])
        result = _make_result(seats=2)
        with patch.object(
            NotifierSkill, "_desktop_notify", new_callable=AsyncMock
        ), patch.object(
            NotifierSkill, "_sound_notify", new_callable=AsyncMock
        ):
            await notifier.send(result)


class TestNotificationPayload:
    def test_payload_creation(self):
        p = NotificationPayload(
            title="테스트",
            message="메시지",
            train_info="1개 열차",
        )
        assert p.title == "테스트"
        assert p.urgency == "high"

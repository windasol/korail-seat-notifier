"""알림 에이전트 (NotifierAgent)

좌석 감지 이벤트를 수신하여 다채널 알림을 발송한다.
쿨다운 관리로 중복 알림을 방지한다.

상태: IDLE → SENDING → COOLDOWN → IDLE
스킬 구성: DesktopNotifySkill + SoundNotifySkill + WebhookSkill (NotifierSkill 내장)
"""

from __future__ import annotations

import asyncio
import logging
from time import monotonic
from typing import Optional

from src.agents.base import BaseAgent
from src.models.config import AgentConfig
from src.models.events import AgentEvent
from src.models.query import CheckResult
from src.skills.notifier import NotifierSkill

logger = logging.getLogger("korail.agent.notifier")


class NotifierAgent(BaseAgent):
    """알림 에이전트

    SEAT_DETECTED 이벤트 수신 → 다채널 병렬 알림 발송
    쿨다운 기간 중에는 중복 알림을 스킵한다.
    """

    def __init__(
        self,
        config: AgentConfig,
        event_bus: Optional[asyncio.Queue] = None,  # type: ignore[type-arg]
        notifier: Optional[NotifierSkill] = None,  # 테스트용 의존성 주입
    ) -> None:
        super().__init__("notifier_agent", event_bus)
        self._config = config
        self._last_notification_time: float = 0.0
        self._notifications_sent: int = 0
        self._inbox: asyncio.Queue[CheckResult] = asyncio.Queue()

        self._notifier = notifier or NotifierSkill(
            methods=config.notification_methods,
            webhook_url=config.webhook_url,
        )

    @property
    def notifications_sent(self) -> int:
        return self._notifications_sent

    @property
    def inbox(self) -> asyncio.Queue[CheckResult]:
        return self._inbox

    async def setup(self) -> None:
        logger.info(
            "NotifierAgent 초기화 완료 (채널: %s, 쿨다운: %.0fs)",
            ",".join(self._config.notification_methods),
            self._config.notification_cooldown,
        )

    async def run(self) -> None:
        """알림 요청 처리 루프"""
        while not self._stop_event.is_set():
            try:
                result = await asyncio.wait_for(
                    self._inbox.get(),
                    timeout=1.0,
                )
                await self._handle_notification(result)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def teardown(self) -> None:
        logger.info("NotifierAgent 정리 완료 (알림 %d회 발송)", self._notifications_sent)

    async def notify(self, result: CheckResult) -> None:
        """Orchestrator가 직접 호출하는 알림 요청"""
        await self._inbox.put(result)

    async def _handle_notification(self, result: CheckResult) -> None:
        """쿨다운 확인 후 알림 발송"""
        now = monotonic()
        cooldown = self._config.notification_cooldown
        time_since_last = now - self._last_notification_time

        if self._last_notification_time > 0 and time_since_last < cooldown:
            remaining = cooldown - time_since_last
            logger.debug("알림 쿨다운 중 (잔여 %.0fs)", remaining)
            return

        available = result.available_trains
        if not available:
            return

        logger.info("알림 발송 시작: %d개 열차", len(available))

        try:
            await self._notifier.send(result)
            self._last_notification_time = now
            self._notifications_sent += 1

            logger.info("알림 발송 완료 (#%d)", self._notifications_sent)

            await self.emit(AgentEvent.NOTIFY_COMPLETE, "orchestrator", {
                "trains_count": len(available),
                "notification_number": self._notifications_sent,
            })

        except Exception as e:
            logger.warning("알림 발송 실패: %s", e)

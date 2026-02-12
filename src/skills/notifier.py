"""알림 스킬: Desktop / Sound / Webhook

다채널 알림을 병렬로 발송한다. 개별 채널 실패는 격리된다.
"""

from __future__ import annotations

import asyncio
import logging
import platform
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("korail.skill.notifier")


@dataclass(frozen=True, slots=True)
class NotificationPayload:
    """알림 페이로드"""

    title: str
    message: str
    train_info: str
    urgency: str = "high"


class NotifierSkill:
    """다채널 알림 스킬"""

    __slots__ = ("_methods", "_webhook_url")

    def __init__(
        self,
        methods: Optional[list[str]] = None,
        webhook_url: str = "",
    ) -> None:
        self._methods = methods or ["desktop", "sound"]
        self._webhook_url = webhook_url

    async def send(self, result: object) -> None:
        """좌석 감지 결과를 알림으로 발송"""
        available = getattr(result, "available_trains", ())
        if not available:
            return

        # 알림 메시지 구성
        lines: list[str] = []
        for t in available[:5]:
            seats = f"일반 {t.general_seats}석"
            if t.special_seats > 0:
                seats += f" / 특실 {t.special_seats}석"
            lines.append(
                f"  {t.train_type} {t.train_no}호 "
                f"{t.departure_time:%H:%M}→{t.arrival_time:%H:%M} "
                f"({seats})"
            )

        payload = NotificationPayload(
            title="코레일 빈자리 발견!",
            message="\n".join(lines),
            train_info=f"{len(available)}개 열차 좌석 가용",
        )

        tasks: list[asyncio.Task[None]] = []
        for method in self._methods:
            if method == "desktop":
                tasks.append(
                    asyncio.ensure_future(self._desktop_notify(payload))
                )
            elif method == "sound":
                tasks.append(
                    asyncio.ensure_future(self._sound_notify())
                )
            elif method == "webhook":
                tasks.append(
                    asyncio.ensure_future(
                        self._webhook_notify(payload, self._webhook_url)
                    )
                )

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    async def _desktop_notify(payload: NotificationPayload) -> None:
        """OS 데스크톱 알림"""
        system = platform.system()

        if system == "Windows":
            try:
                from winotify import Notification  # type: ignore[import-untyped]

                toast = Notification(
                    app_id="Korail Seat Notifier",
                    title=payload.title,
                    msg=payload.message[:200],
                )
                toast.show()
            except ImportError:
                import subprocess

                msg = payload.message.replace('"', '`"')[:150]
                subprocess.Popen(  # noqa: S603
                    [
                        "powershell", "-Command",
                        '[System.Reflection.Assembly]::LoadWithPartialName'
                        '("System.Windows.Forms") | Out-Null; '
                        "$n=New-Object System.Windows.Forms.NotifyIcon; "
                        "$n.Icon=[System.Drawing.SystemIcons]::Information; "
                        "$n.Visible=$true; "
                        f'$n.ShowBalloonTip(5000,"{payload.title}","{msg}",'
                        "[System.Windows.Forms.ToolTipIcon]::Info)",
                    ],
                    creationflags=0x08000000,
                )

        elif system == "Darwin":
            import subprocess

            subprocess.Popen(  # noqa: S603
                [
                    "osascript", "-e",
                    f'display notification "{payload.message[:150]}" '
                    f'with title "{payload.title}" sound name "Glass"',
                ],
            )

        elif system == "Linux":
            import subprocess

            subprocess.Popen(  # noqa: S603
                [
                    "notify-send", payload.title,
                    payload.message[:200],
                    "-u", "critical",
                ],
            )

    @staticmethod
    async def _sound_notify() -> None:
        """알림음 재생"""
        system = platform.system()
        if system == "Windows":
            try:
                import winsound  # type: ignore[import-not-found]

                for _ in range(3):
                    winsound.Beep(1000, 500)
                    await asyncio.sleep(0.3)
            except ImportError:
                print("\a" * 3)
        else:
            print("\a" * 3)

    @staticmethod
    async def _webhook_notify(
        payload: NotificationPayload,
        webhook_url: str,
    ) -> None:
        """Webhook 알림 (Slack/Discord)"""
        if not webhook_url:
            return

        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    webhook_url,
                    json={"text": f"*{payload.title}*\n{payload.message}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception as e:
            logger.warning("Webhook 알림 실패: %s", e)

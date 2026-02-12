"""에이전트 기본 인터페이스

모든 에이전트는 BaseAgent를 상속하여 공통 라이프사이클을 따른다.
라이프사이클: INIT → READY → ACTIVE → DRAINING → RECOVERING → OFF
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Optional

from src.models.events import AgentEvent, AgentMessage


class AgentLifecycle(Enum):
    """에이전트 라이프사이클 상태"""
    INIT = auto()
    READY = auto()
    ACTIVE = auto()
    DRAINING = auto()
    RECOVERING = auto()
    OFF = auto()


class BaseAgent(ABC):
    """에이전트 기본 추상 클래스

    모든 에이전트는 이 클래스를 상속받아:
    - setup(): 초기화 작업
    - run(): 메인 실행 루프
    - teardown(): 정리 작업
    을 구현한다.
    """

    def __init__(
        self,
        agent_id: str,
        event_bus: Optional[asyncio.Queue[AgentMessage]] = None,
    ) -> None:
        self._id = agent_id
        self._event_bus = event_bus
        self._lifecycle = AgentLifecycle.INIT
        self._stop_event = asyncio.Event()
        self._logger = logging.getLogger(f"korail.agent.{agent_id}")

    @property
    def agent_id(self) -> str:
        return self._id

    @property
    def lifecycle(self) -> AgentLifecycle:
        return self._lifecycle

    @property
    def is_active(self) -> bool:
        return self._lifecycle == AgentLifecycle.ACTIVE

    def _set_lifecycle(self, state: AgentLifecycle) -> None:
        self._logger.debug("라이프사이클: %s → %s", self._lifecycle.name, state.name)
        self._lifecycle = state

    async def emit(self, event: str, target: str, payload: object = None) -> None:
        """이벤트 버스에 메시지 발송"""
        if self._event_bus is None:
            return
        msg = AgentMessage(
            event=event,
            source=self._id,
            target=target,
            payload=payload,
        )
        await self._event_bus.put(msg)

    def request_stop(self) -> None:
        """외부에서 에이전트 중지 요청"""
        self._stop_event.set()

    @abstractmethod
    async def setup(self) -> None:
        """초기화: 의존성 주입, 설정 로드"""

    @abstractmethod
    async def run(self) -> None:
        """메인 실행 루프"""

    @abstractmethod
    async def teardown(self) -> None:
        """정리: 리소스 해제"""

    async def start(self) -> None:
        """에이전트 전체 라이프사이클 실행"""
        try:
            self._set_lifecycle(AgentLifecycle.INIT)
            await self.setup()
            self._set_lifecycle(AgentLifecycle.READY)
            self._set_lifecycle(AgentLifecycle.ACTIVE)
            await self.run()
        except Exception as e:
            self._logger.error("에이전트 실행 오류: %s", e)
            self._set_lifecycle(AgentLifecycle.RECOVERING)
            raise
        finally:
            self._set_lifecycle(AgentLifecycle.DRAINING)
            await self.teardown()
            self._set_lifecycle(AgentLifecycle.OFF)

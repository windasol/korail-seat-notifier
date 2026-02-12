"""입력 처리 에이전트 (InputAgent)

사용자 입력을 수신, 파싱, 검증하여 TrainQuery 불변 객체를 생성한다.
스킬 구성: ParserSkill → StationSkill → ValidationSkill
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from src.agents.base import BaseAgent
from src.models.events import AgentEvent
from src.models.query import TrainQuery
from src.skills.parser import ParserSkill
from src.skills.validation import ValidationSkill

logger = logging.getLogger("korail.agent.input")


class InputAgent(BaseAgent):
    """입력 처리 에이전트 (Stateless: 요청-응답 방식)

    CLI args 또는 대화형 입력 → 검증된 TrainQuery 반환
    """

    def __init__(
        self,
        event_bus: Optional[asyncio.Queue] = None,  # type: ignore[type-arg]
    ) -> None:
        super().__init__("input_agent", event_bus)
        self._parser = ParserSkill()
        self._validator = ValidationSkill()

    async def setup(self) -> None:
        logger.debug("InputAgent 초기화 완료")

    async def run(self) -> None:
        """InputAgent는 stateless — process() 직접 호출 방식으로 동작"""
        pass

    async def teardown(self) -> None:
        logger.debug("InputAgent 정리 완료")

    async def process_cli(self, args: object) -> TrainQuery:
        """CLI argparse.Namespace → 검증된 TrainQuery

        발생 가능한 예외: ValueError (검증 실패)
        """
        import argparse

        if not isinstance(args, argparse.Namespace):
            raise TypeError("args는 argparse.Namespace 이어야 합니다")

        data = self._parser.parse_cli(args)
        query = self._validator.validate_query(data)

        logger.info("입력 처리 완료: %s", query.summary())
        await self.emit(AgentEvent.QUERY_READY, "orchestrator", query)
        return query

    async def process_interactive(self, raw_inputs: dict[str, str]) -> TrainQuery:
        """대화형 입력 dict → 검증된 TrainQuery

        발생 가능한 예외: ValueError (검증 실패)
        """
        data = self._parser.parse_interactive(raw_inputs)
        query = self._validator.validate_query(data)

        logger.info("입력 처리 완료: %s", query.summary())
        await self.emit(AgentEvent.QUERY_READY, "orchestrator", query)
        return query

    async def process_query(self, query: TrainQuery) -> TrainQuery:
        """이미 생성된 TrainQuery 검증 후 통과

        main.py에서 직접 TrainQuery를 전달받는 경우 사용
        """
        logger.info("쿼리 전달 완료: %s", query.summary())
        await self.emit(AgentEvent.QUERY_READY, "orchestrator", query)
        return query

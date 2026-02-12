"""InputAgent 단위 테스트"""

from __future__ import annotations

import asyncio
from datetime import date, time
from unittest.mock import MagicMock

import pytest

from src.agents.input_agent import InputAgent
from src.models.query import TrainQuery


class TestInputAgentProcessQuery:
    """이미 생성된 TrainQuery 전달 테스트"""

    @pytest.mark.asyncio
    async def test_process_query_returns_same_query(
        self, sample_query: TrainQuery
    ) -> None:
        agent = InputAgent()
        result = await agent.process_query(sample_query)
        assert result == sample_query

    @pytest.mark.asyncio
    async def test_process_query_emits_event(self, sample_query: TrainQuery) -> None:
        bus: asyncio.Queue = asyncio.Queue()
        agent = InputAgent(event_bus=bus)

        await agent.process_query(sample_query)

        assert not bus.empty()
        msg = await bus.get()
        assert msg.event == "query.ready"
        assert msg.source == "input_agent"
        assert msg.payload == sample_query


class TestInputAgentProcessInteractive:
    """대화형 입력 처리 테스트"""

    @pytest.mark.asyncio
    async def test_valid_interactive_input(self) -> None:
        agent = InputAgent()
        raw = {
            "departure": "서울",
            "arrival": "부산",
            "date": "20260301",
            "time_start": "0800",
            "time_end": "1200",
            "train_type": "KTX",
            "seat_type": "일반실",
            "passengers": "1",
        }
        query = await agent.process_interactive(raw)
        assert query.departure_station == "서울"
        assert query.arrival_station == "부산"
        assert query.departure_date == date(2026, 3, 1)
        assert query.preferred_time_start == time(8, 0)
        assert query.preferred_time_end == time(12, 0)

    @pytest.mark.asyncio
    async def test_invalid_station_raises_error(self) -> None:
        agent = InputAgent()
        raw = {
            "departure": "없는역",
            "arrival": "부산",
            "date": "20260301",
            "time_start": "0800",
            "time_end": "1200",
        }
        with pytest.raises(ValueError):
            await agent.process_interactive(raw)

    @pytest.mark.asyncio
    async def test_same_station_raises_error(self) -> None:
        agent = InputAgent()
        raw = {
            "departure": "서울",
            "arrival": "서울",
            "date": "20260301",
            "time_start": "0800",
            "time_end": "1200",
        }
        with pytest.raises(ValueError):
            await agent.process_interactive(raw)


class TestInputAgentLifecycle:
    """에이전트 라이프사이클 테스트"""

    @pytest.mark.asyncio
    async def test_setup_and_teardown(self) -> None:
        agent = InputAgent()
        await agent.setup()
        await agent.teardown()

    @pytest.mark.asyncio
    async def test_run_is_noop(self) -> None:
        agent = InputAgent()
        await agent.run()  # stateless - 즉시 반환해야 함

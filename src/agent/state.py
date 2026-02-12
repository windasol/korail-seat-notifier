"""에이전트 상태 머신

상태 전이 규칙을 정의하고 검증한다.
"""

from __future__ import annotations

from enum import Enum, auto


class AgentState(Enum):
    IDLE = auto()
    MONITORING = auto()
    DETECTED = auto()
    NOTIFIED = auto()
    STOPPED = auto()
    ERROR = auto()


# 허용된 상태 전이 맵: {현재상태: {허용되는 다음 상태들}}
_VALID_TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    AgentState.IDLE: frozenset({AgentState.MONITORING, AgentState.STOPPED}),
    AgentState.MONITORING: frozenset({
        AgentState.DETECTED, AgentState.ERROR, AgentState.STOPPED,
    }),
    AgentState.DETECTED: frozenset({
        AgentState.NOTIFIED, AgentState.MONITORING, AgentState.STOPPED,
    }),
    AgentState.NOTIFIED: frozenset({
        AgentState.MONITORING, AgentState.STOPPED,
    }),
    AgentState.ERROR: frozenset({
        AgentState.MONITORING, AgentState.STOPPED,
    }),
    AgentState.STOPPED: frozenset(),  # 터미널 상태
}


def validate_transition(current: AgentState, target: AgentState) -> bool:
    """상태 전이가 유효한지 검증"""
    allowed = _VALID_TRANSITIONS.get(current, frozenset())
    return target in allowed

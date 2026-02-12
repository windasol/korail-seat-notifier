"""에이전트 간 통신 이벤트 모델"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any


class AgentEvent:
    """에이전트 이벤트 타입 상수"""

    QUERY_READY = "query.ready"
    POLL_START = "poll.start"
    POLL_RESULT = "poll.result"
    SEAT_DETECTED = "seat.detected"
    NOTIFY_REQUEST = "notify.request"
    NOTIFY_COMPLETE = "notify.complete"
    HEALTH_WARNING = "health.warning"
    HEALTH_CRITICAL = "health.critical"
    SESSION_STOP = "session.stop"


@dataclass(frozen=True, slots=True)
class AgentMessage:
    """에이전트 간 메시지"""

    event: str
    source: str
    target: str
    payload: Any
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            object.__setattr__(self, "timestamp", monotonic())

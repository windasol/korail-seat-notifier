"""에이전트 설정 모델"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    """에이전트 설정 - 성능/메모리 튜닝 파라미터"""

    # Polling 설정
    base_interval: float = 30.0
    max_interval: float = 300.0
    backoff_multiplier: float = 1.5
    jitter_range: float = 5.0

    # 리소스 제한
    max_session_duration: float = 21600.0   # 6시간
    max_consecutive_errors: int = 10
    max_requests_per_session: int = 720

    # 메모리 관리
    max_log_entries: int = 100
    gc_interval: int = 50

    # 알림 설정
    notification_cooldown: float = 60.0
    notification_methods: list[str] = field(
        default_factory=lambda: ["desktop", "sound"]
    )
    webhook_url: str = ""

    # HTTP 설정
    request_timeout: float = 15.0
    connect_timeout: float = 5.0
    max_connections: int = 3

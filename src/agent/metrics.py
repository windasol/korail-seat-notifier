"""에이전트 런타임 메트릭 수집"""

from __future__ import annotations

import sys
from time import monotonic


class AgentMetrics:
    """런타임 메트릭 수집"""

    __slots__ = (
        "total_requests", "successful_checks", "failed_checks",
        "seats_detected_count", "notifications_sent",
        "_response_times", "peak_memory_mb",
        "_start_time",
    )

    def __init__(self) -> None:
        self.total_requests: int = 0
        self.successful_checks: int = 0
        self.failed_checks: int = 0
        self.seats_detected_count: int = 0
        self.notifications_sent: int = 0
        self._response_times: list[float] = []
        self.peak_memory_mb: float = 0.0
        self._start_time: float = monotonic()

    @property
    def avg_response_time_ms(self) -> float:
        if not self._response_times:
            return 0.0
        return sum(self._response_times) / len(self._response_times)

    @property
    def session_duration_s(self) -> float:
        return monotonic() - self._start_time

    def record_request(self, success: bool, elapsed_ms: float) -> None:
        self.total_requests += 1
        if success:
            self.successful_checks += 1
        else:
            self.failed_checks += 1
        self._response_times.append(elapsed_ms)
        # 최근 100개만 유지
        if len(self._response_times) > 100:
            self._response_times = self._response_times[-50:]

    def record_detection(self) -> None:
        self.seats_detected_count += 1

    def record_notification(self) -> None:
        self.notifications_sent += 1

    def update_memory(self) -> None:
        try:
            import psutil
            process = psutil.Process()
            mem_mb = process.memory_info().rss / (1024 * 1024)
        except ImportError:
            mem_mb = sys.getsizeof(self) / (1024 * 1024)
        self.peak_memory_mb = max(self.peak_memory_mb, mem_mb)

    def summary(self) -> str:
        duration = self.session_duration_s
        success_rate = (
            self.successful_checks / max(self.total_requests, 1) * 100
        )
        return (
            f"=== 세션 요약 ===\n"
            f"  경과 시간: {duration / 60:.1f}분\n"
            f"  총 요청: {self.total_requests}회 "
            f"(성공률: {success_rate:.1f}%)\n"
            f"  좌석 감지: {self.seats_detected_count}회\n"
            f"  알림 발송: {self.notifications_sent}회\n"
            f"  평균 응답: {self.avg_response_time_ms:.0f}ms\n"
            f"  최대 메모리: {self.peak_memory_mb:.1f}MB"
        )

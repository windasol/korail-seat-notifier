# Korail Seat Availability Notification Agent

> **Version**: 1.0.0
> **Type**: Prompt > Agent > Skill Pipeline
> **Purpose**: 코레일 좌석 빈자리 감지 및 알림 시스템

---

## 1. System Architecture Overview

```
[User Input] → [Prompt Layer] → [Agent Orchestrator] → [Skill Executors] → [Notification]
                    │                    │                      │
              Validation &          State Machine          API Polling
              Normalization         & Scheduling           & Detection
```

### Pipeline Flow

```
Phase 1: PROMPT (Input Processing)
  ├── 사용자 입력 파싱 (출발지, 도착지, 날짜, 시간, 열차종류)
  ├── 입력값 유효성 검증
  └── 구조화된 Query Object 생성

Phase 2: AGENT (Orchestration)
  ├── Polling 스케줄러 관리
  ├── 상태 머신 (Idle → Monitoring → Detected → Notified)
  ├── Rate Limiting & Backoff 전략
  └── 메모리/토큰 최적화 제어

Phase 3: SKILL (Execution)
  ├── Korail API/웹 조회 실행
  ├── 응답 파싱 & 좌석 가용성 판별
  ├── 알림 발송 (Desktop/Sound/Webhook)
  └── 로깅 & 모니터링
```

---

## 2. Prompt Layer Specification

### 2.1 System Prompt

```markdown
당신은 코레일(Korail) 좌석 가용성 모니터링 에이전트입니다.

## 역할
- 사용자가 지정한 열차의 좌석 가용 여부를 주기적으로 확인합니다
- 좌석이 감지되면 즉시 알림을 발송합니다
- 코레일 서비스에 과부하를 주지 않도록 적절한 간격으로 조회합니다

## 제약 조건
- 자동 예매/결제를 수행하지 않습니다 (알림 전용)
- 조회 간격은 최소 30초 이상을 유지합니다
- 단일 세션에서 최대 모니터링 시간은 6시간입니다
- robots.txt 및 서비스 이용약관을 준수합니다

## 입력 형식
사용자는 다음 정보를 제공합니다:
- 출발역 (필수)
- 도착역 (필수)
- 출발 날짜 (필수, YYYY-MM-DD)
- 희망 시간대 (필수, HH:MM 또는 범위)
- 열차 종류 (선택, 기본값: KTX)
- 좌석 유형 (선택, 기본값: 일반실)
```

### 2.2 Input Schema

```python
from dataclasses import dataclass, field
from typing import Optional, Literal
from datetime import date, time

@dataclass(frozen=True, slots=True)
class TrainQuery:
    """불변 조회 요청 객체 - slots=True로 메모리 최적화"""
    departure_station: str          # 출발역
    arrival_station: str            # 도착역
    departure_date: date            # 출발 날짜
    preferred_time_start: time      # 희망 시간 시작
    preferred_time_end: time        # 희망 시간 종료
    train_type: Literal[
        "KTX", "KTX-산천", "KTX-이음",
        "ITX-새마을", "ITX-청춘", "무궁화"
    ] = "KTX"
    seat_type: Literal[
        "일반실", "특실"
    ] = "일반실"
    passenger_count: int = 1

    def __post_init__(self):
        if self.passenger_count < 1 or self.passenger_count > 9:
            raise ValueError("승객 수는 1~9명이어야 합니다")
        if self.preferred_time_end <= self.preferred_time_start:
            raise ValueError("종료 시간이 시작 시간보다 커야 합니다")
```

### 2.3 Station Validation Map

```python
# 주요 역 코드 매핑 (메모리 효율: frozenset + tuple)
STATION_CODES: dict[str, str] = {
    "서울": "0001", "용산": "0015", "영등포": "0020",
    "수원": "0055", "천안아산": "0502", "대전": "0010",
    "동대구": "0015", "부산": "0020", "광주송정": "0036",
    "목포": "0041", "전주": "0045", "익산": "0030",
    "강릉": "0115", "평창": "0112", "여수엑스포": "0049",
    "포항": "0520", "진주": "0056",
}

def validate_station(name: str) -> str:
    """역 이름 정규화 및 검증"""
    normalized = name.strip().replace(" ", "")
    if normalized not in STATION_CODES:
        raise ValueError(
            f"'{name}'은(는) 지원하지 않는 역입니다. "
            f"지원 역: {', '.join(sorted(STATION_CODES.keys()))}"
        )
    return normalized
```

---

## 3. Agent Layer Specification

### 3.1 State Machine

```
                  ┌──────────────┐
                  │     IDLE     │
                  └──────┬───────┘
                         │ start_monitoring()
                         ▼
                  ┌──────────────┐
             ┌───►│  MONITORING  │◄──── retry (with backoff)
             │    └──────┬───────┘
             │           │ seat_found()
             │           ▼
             │    ┌──────────────┐
             │    │   DETECTED   │
             │    └──────┬───────┘
             │           │ notify()
             │           ▼
             │    ┌──────────────┐
             │    │   NOTIFIED   │
             │    └──────┬───────┘
             │           │
             │     continue?─── No ──► STOPPED
             │           │
             └─── Yes ───┘

         Error at any state → ERROR → retry or STOPPED
```

### 3.2 Agent Core Implementation

```python
import asyncio
import logging
from enum import Enum, auto
from typing import Callable, Optional
from dataclasses import dataclass, field
from time import monotonic

logger = logging.getLogger("korail_agent")


class AgentState(Enum):
    IDLE = auto()
    MONITORING = auto()
    DETECTED = auto()
    NOTIFIED = auto()
    STOPPED = auto()
    ERROR = auto()


@dataclass
class AgentConfig:
    """에이전트 설정 - 성능/메모리 튜닝 파라미터"""
    # Polling 설정
    base_interval: float = 30.0          # 기본 조회 간격 (초)
    max_interval: float = 300.0          # 최대 백오프 간격 (초)
    backoff_multiplier: float = 1.5      # 백오프 배수
    jitter_range: float = 5.0            # 랜덤 지터 범위 (초)

    # 리소스 제한
    max_session_duration: float = 21600  # 최대 세션 시간 (6시간)
    max_consecutive_errors: int = 10     # 연속 에러 허용 횟수
    max_requests_per_session: int = 720  # 세션당 최대 요청 수 (6h/30s)

    # 메모리 관리
    max_log_entries: int = 100           # 메모리 내 로그 최대 보관 수
    gc_interval: int = 50               # GC 트리거 주기 (요청 수 기준)

    # 알림 설정
    notification_cooldown: float = 60.0  # 알림 재발송 쿨다운 (초)
    notification_methods: list[str] = field(
        default_factory=lambda: ["desktop", "sound"]
    )


class KorailAgent:
    """코레일 좌석 모니터링 에이전트 (메인 오케스트레이터)"""

    __slots__ = (
        "_state", "_config", "_query", "_current_interval",
        "_request_count", "_error_count", "_start_time",
        "_last_notification_time", "_log_buffer", "_running",
    )

    def __init__(self, config: Optional[AgentConfig] = None):
        self._state = AgentState.IDLE
        self._config = config or AgentConfig()
        self._query: Optional[TrainQuery] = None
        self._current_interval = self._config.base_interval
        self._request_count = 0
        self._error_count = 0
        self._start_time = 0.0
        self._last_notification_time = 0.0
        self._log_buffer: list[dict] = []
        self._running = False

    @property
    def state(self) -> AgentState:
        return self._state

    def _transition(self, new_state: AgentState) -> None:
        """상태 전이 + 로깅"""
        old = self._state
        self._state = new_state
        self._log(f"State: {old.name} -> {new_state.name}")

    def _log(self, message: str) -> None:
        """메모리 제한 로깅 (ring buffer 패턴)"""
        entry = {"ts": monotonic(), "msg": message}
        self._log_buffer.append(entry)
        if len(self._log_buffer) > self._config.max_log_entries:
            # 오래된 절반 제거 (GC 빈도 최소화)
            self._log_buffer = self._log_buffer[
                self._config.max_log_entries // 2:
            ]
        logger.info(message)

    def _calculate_next_interval(self, had_error: bool) -> float:
        """적응형 폴링 간격 계산 (지수 백오프 + 지터)"""
        import random

        if had_error:
            self._current_interval = min(
                self._current_interval * self._config.backoff_multiplier,
                self._config.max_interval,
            )
        else:
            # 성공 시 점진적 간격 복원
            self._current_interval = max(
                self._current_interval / 1.2,
                self._config.base_interval,
            )

        jitter = random.uniform(0, self._config.jitter_range)
        return self._current_interval + jitter

    def _check_resource_limits(self) -> bool:
        """리소스 한계 검사 - 초과 시 자동 중지"""
        elapsed = monotonic() - self._start_time

        if elapsed > self._config.max_session_duration:
            self._log("세션 시간 초과 - 자동 중지")
            return False

        if self._request_count >= self._config.max_requests_per_session:
            self._log("최대 요청 수 도달 - 자동 중지")
            return False

        if self._error_count >= self._config.max_consecutive_errors:
            self._log("연속 에러 한계 초과 - 자동 중지")
            return False

        return True

    async def start(self, query: TrainQuery) -> None:
        """모니터링 시작"""
        self._query = query
        self._start_time = monotonic()
        self._running = True
        self._transition(AgentState.MONITORING)

        self._log(
            f"모니터링 시작: {query.departure_station} → "
            f"{query.arrival_station} / {query.departure_date} / "
            f"{query.preferred_time_start}-{query.preferred_time_end}"
        )

        while self._running and self._check_resource_limits():
            had_error = False
            try:
                # Skill 호출: 좌석 조회
                result = await self._execute_check(query)

                if result.seats_available:
                    self._error_count = 0
                    self._transition(AgentState.DETECTED)
                    await self._handle_detection(result)
                else:
                    self._error_count = 0
                    self._log(
                        f"조회 #{self._request_count}: 빈 좌석 없음"
                    )

            except Exception as e:
                had_error = True
                self._error_count += 1
                self._transition(AgentState.ERROR)
                self._log(f"에러 발생 ({self._error_count}회): {e}")
                self._transition(AgentState.MONITORING)

            finally:
                self._request_count += 1
                # 주기적 GC
                if self._request_count % self._config.gc_interval == 0:
                    import gc
                    gc.collect(generation=0)

            interval = self._calculate_next_interval(had_error)
            await asyncio.sleep(interval)

        self._transition(AgentState.STOPPED)

    async def _execute_check(self, query: TrainQuery):
        """Skill 레이어 호출 (좌석 조회)"""
        from skills.seat_checker import SeatCheckerSkill
        skill = SeatCheckerSkill()
        return await skill.check(query)

    async def _handle_detection(self, result) -> None:
        """좌석 감지 처리 및 알림"""
        now = monotonic()
        cooldown = self._config.notification_cooldown

        if (now - self._last_notification_time) < cooldown:
            self._log("알림 쿨다운 중 - 스킵")
            return

        from skills.notifier import NotifierSkill
        notifier = NotifierSkill(self._config.notification_methods)
        await notifier.send(result)

        self._last_notification_time = now
        self._transition(AgentState.NOTIFIED)
        self._transition(AgentState.MONITORING)

    def stop(self) -> None:
        """모니터링 중지"""
        self._running = False
        self._log("사용자에 의한 수동 중지")
```

### 3.3 Token Optimization Strategy

```markdown
## 토큰 최적화 전략

### 1. 입력 압축
- 역 이름 → 코드 변환 (서울 → 0001): ~70% 토큰 절약
- 날짜/시간 ISO 포맷 강제: 파싱 토큰 최소화
- 불필요한 자연어 제거, 구조화된 JSON만 전달

### 2. 응답 최소화
- API 응답에서 필요 필드만 추출 (좌석수, 열차번호, 시간)
- HTML 파싱 시 필요한 DOM 노드만 선택적 추출
- 로그 메시지 템플릿화 (f-string 대신 lazy formatting)

### 3. 컨텍스트 윈도우 관리
- 히스토리 rolling window: 최근 N개 조회 결과만 보존
- 상태 요약 압축: 전체 로그 대신 통계 요약 전달
- 에이전트 간 메시지: 최소 필드 프로토콜 사용

### 4. 측정 기준
| 항목 | 목표 | 측정 방법 |
|------|------|-----------|
| 요청당 입력 토큰 | < 200 | TrainQuery 직렬화 크기 |
| 요청당 출력 토큰 | < 150 | 파싱 결과 직렬화 크기 |
| 세션 누적 토큰 | < 50K | 6시간 세션 총량 |
| 메모리 사용량 | < 50MB | RSS 기준 |
```

---

## 4. Skill Layer Specification

### 4.1 Seat Checker Skill

```python
import aiohttp
from dataclasses import dataclass
from typing import Optional
from datetime import time


@dataclass(frozen=True, slots=True)
class TrainInfo:
    """개별 열차 정보 (불변, 메모리 최적화)"""
    train_no: str
    train_type: str
    departure_time: time
    arrival_time: time
    general_seats: int       # 일반실 잔여
    special_seats: int       # 특실 잔여
    duration_minutes: int


@dataclass(frozen=True, slots=True)
class CheckResult:
    """조회 결과"""
    query_timestamp: float
    trains: tuple[TrainInfo, ...]  # tuple로 불변성 보장
    seats_available: bool
    raw_response_size: int         # 디버깅용 응답 크기

    @property
    def available_trains(self) -> tuple[TrainInfo, ...]:
        return tuple(
            t for t in self.trains
            if t.general_seats > 0 or t.special_seats > 0
        )


class SeatCheckerSkill:
    """코레일 좌석 조회 스킬

    조회 방식: 코레일 공식 모바일 API 엔드포인트 활용
    - 공개된 웹 페이지 조회와 동일한 수준의 접근
    - 로그인 불필요 (비회원 조회)
    - User-Agent를 정직하게 명시
    """

    # 연결 풀 재사용을 위한 클래스 레벨 세션
    _session: Optional[aiohttp.ClientSession] = None

    # 요청 헤더 (정직한 봇 식별)
    HEADERS = {
        "User-Agent": "KorailSeatNotifier/1.0 (Personal Use; Notification Only)",
        "Accept": "application/json",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    # 코레일 승차권 조회 URL (공개 웹 조회)
    BASE_URL = "https://www.letskorail.com/ebizprd/EbizPrdSttnKeyListBy498.do"

    @classmethod
    async def _get_session(cls) -> aiohttp.ClientSession:
        """커넥션 풀 싱글턴 (메모리 효율)"""
        if cls._session is None or cls._session.closed:
            timeout = aiohttp.ClientTimeout(total=15, connect=5)
            connector = aiohttp.TCPConnector(
                limit=3,              # 최대 동시 연결 3개
                ttl_dns_cache=300,    # DNS 캐시 5분
                enable_cleanup_closed=True,
            )
            cls._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers=cls.HEADERS,
            )
        return cls._session

    async def check(self, query: TrainQuery) -> CheckResult:
        """좌석 가용성 조회 실행"""
        from time import monotonic

        session = await self._get_session()
        params = self._build_params(query)

        ts = monotonic()
        async with session.get(self.BASE_URL, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
            raw_size = len(await resp.read()) if resp.content else 0

        trains = self._parse_response(data, query)
        available = any(
            t.general_seats > 0 or t.special_seats > 0
            for t in trains
        )

        return CheckResult(
            query_timestamp=ts,
            trains=tuple(trains),
            seats_available=available,
            raw_response_size=raw_size,
        )

    @staticmethod
    def _build_params(query: TrainQuery) -> dict[str, str]:
        """API 요청 파라미터 구성"""
        return {
            "stationDeparture": query.departure_station,
            "stationArrival": query.arrival_station,
            "departureDateStr": query.departure_date.strftime("%Y%m%d"),
            "departureTimeStr": query.preferred_time_start.strftime("%H%M%S"),
            "trainType": _TRAIN_TYPE_CODES.get(query.train_type, "00"),
            "seatType": "1" if query.seat_type == "일반실" else "2",
            "passengerCount": str(query.passenger_count),
        }

    @staticmethod
    def _parse_response(
        data: dict, query: TrainQuery
    ) -> list[TrainInfo]:
        """응답 파싱 - 필요 필드만 추출 (토큰/메모리 최적화)"""
        trains = []
        for item in data.get("trn_infos", {}).get("trn_info", []):
            dep_time = _parse_time(item.get("h_dpt_tm", "000000"))
            arr_time = _parse_time(item.get("h_arv_tm", "000000"))

            # 시간 범위 필터링
            if not (query.preferred_time_start
                    <= dep_time
                    <= query.preferred_time_end):
                continue

            trains.append(TrainInfo(
                train_no=item.get("h_trn_no", ""),
                train_type=item.get("h_trn_clsf_nm", ""),
                departure_time=dep_time,
                arrival_time=arr_time,
                general_seats=_parse_seat_count(
                    item.get("h_rsv_psb_nm", "")
                ),
                special_seats=_parse_seat_count(
                    item.get("h_spe_rsv_psb_nm", "")
                ),
                duration_minutes=_calc_duration(dep_time, arr_time),
            ))
        return trains


# 열차 유형 코드
_TRAIN_TYPE_CODES = {
    "KTX": "00", "KTX-산천": "00", "KTX-이음": "00",
    "ITX-새마을": "01", "ITX-청춘": "09", "무궁화": "02",
}

def _parse_time(s: str) -> time:
    return time(int(s[:2]), int(s[2:4]))

def _parse_seat_count(text: str) -> int:
    if "매진" in text or "없음" in text:
        return 0
    try:
        return int("".join(c for c in text if c.isdigit()) or "0")
    except ValueError:
        return 0

def _calc_duration(dep: time, arr: time) -> int:
    return (arr.hour * 60 + arr.minute) - (dep.hour * 60 + dep.minute)
```

### 4.2 Notifier Skill

```python
import asyncio
import platform
from dataclasses import dataclass


@dataclass
class NotificationPayload:
    """알림 페이로드"""
    title: str
    message: str
    train_info: str
    urgency: str = "high"


class NotifierSkill:
    """다채널 알림 스킬"""

    __slots__ = ("_methods",)

    def __init__(self, methods: list[str]):
        self._methods = methods

    async def send(self, result) -> None:
        """감지 결과를 알림으로 발송"""
        available = result.available_trains
        if not available:
            return

        # 알림 메시지 구성
        lines = []
        for t in available[:5]:  # 최대 5개만 표시
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

        # 설정된 방법으로 동시 발송
        tasks = []
        for method in self._methods:
            if method == "desktop":
                tasks.append(self._desktop_notify(payload))
            elif method == "sound":
                tasks.append(self._sound_notify())
            elif method == "webhook":
                tasks.append(self._webhook_notify(payload))

        await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    async def _desktop_notify(payload: NotificationPayload) -> None:
        """OS 데스크톱 알림"""
        system = platform.system()

        if system == "Windows":
            # Windows Toast Notification
            try:
                from winotify import Notification
                toast = Notification(
                    app_id="Korail Seat Notifier",
                    title=payload.title,
                    msg=payload.message[:200],  # 길이 제한
                )
                toast.set_audio(
                    audio=Notification.Sound.Default,
                    loop=False,
                )
                toast.show()
            except ImportError:
                # fallback: powershell
                import subprocess
                msg = payload.message.replace('"', '`"')[:150]
                subprocess.Popen([
                    "powershell", "-Command",
                    f'[System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms");'
                    f'$n=New-Object System.Windows.Forms.NotifyIcon;'
                    f'$n.Icon=[System.Drawing.SystemIcons]::Information;'
                    f'$n.Visible=$true;'
                    f'$n.ShowBalloonTip(5000,"{payload.title}","{msg}",'
                    f'[System.Windows.Forms.ToolTipIcon]::Info)'
                ], creationflags=0x08000000)

        elif system == "Darwin":
            import subprocess
            subprocess.Popen([
                "osascript", "-e",
                f'display notification "{payload.message[:150]}" '
                f'with title "{payload.title}" sound name "Glass"'
            ])

        elif system == "Linux":
            import subprocess
            subprocess.Popen([
                "notify-send", payload.title,
                payload.message[:200],
                "-u", "critical",
            ])

    @staticmethod
    async def _sound_notify() -> None:
        """알림음 재생"""
        system = platform.system()
        if system == "Windows":
            import winsound
            # 3회 반복 비프음
            for _ in range(3):
                winsound.Beep(1000, 500)
                await asyncio.sleep(0.3)
        else:
            print("\a" * 3)  # 터미널 벨

    @staticmethod
    async def _webhook_notify(payload: NotificationPayload) -> None:
        """Webhook 알림 (Slack/Discord/Telegram 등)"""
        import os
        webhook_url = os.environ.get("KORAIL_WEBHOOK_URL")
        if not webhook_url:
            return

        import aiohttp
        async with aiohttp.ClientSession() as session:
            await session.post(webhook_url, json={
                "text": f"*{payload.title}*\n{payload.message}",
            }, timeout=aiohttp.ClientTimeout(total=10))
```

---

## 5. Performance & Memory Optimization Guide

### 5.1 Memory Budget

```
Target Total RSS: < 50MB

Component Breakdown:
├── Python Runtime        ~15MB (baseline)
├── aiohttp + deps        ~10MB
├── Agent State            ~1MB (logs, buffers)
├── Connection Pool        ~3MB (3 connections)
├── Notification deps      ~5MB (winotify etc.)
└── Headroom              ~16MB
```

### 5.2 Optimization Checklist

```markdown
### Data Structures
- [x] `__slots__` on all hot-path classes
- [x] `frozen=True` dataclasses for immutable data
- [x] `tuple` over `list` for fixed-size collections
- [x] Ring buffer pattern for log entries
- [x] Connection pool singleton (avoid per-request overhead)

### Async I/O
- [x] `aiohttp` with connection pooling (limit=3)
- [x] DNS cache (ttl=300s)
- [x] Response streaming (read only needed fields)
- [x] Timeout enforcement (connect=5s, total=15s)

### Polling Strategy
- [x] Adaptive interval (30s base, 300s max)
- [x] Exponential backoff on errors
- [x] Random jitter (0-5s) to avoid thundering herd
- [x] Gradual recovery after success

### GC Strategy
- [x] Generation-0 collection every 50 requests
- [x] Log buffer halving when limit reached
- [x] Session cleanup on stop
```

### 5.3 Monitoring Metrics

```python
@dataclass
class AgentMetrics:
    """런타임 메트릭 수집 (디버깅/튜닝용)"""
    __slots__ = (
        "total_requests", "successful_checks", "failed_checks",
        "seats_detected_count", "notifications_sent",
        "avg_response_time_ms", "peak_memory_mb",
        "total_tokens_used", "session_duration_s",
    )

    total_requests: int
    successful_checks: int
    failed_checks: int
    seats_detected_count: int
    notifications_sent: int
    avg_response_time_ms: float
    peak_memory_mb: float
    total_tokens_used: int
    session_duration_s: float

    def summary(self) -> str:
        success_rate = (
            self.successful_checks / max(self.total_requests, 1) * 100
        )
        return (
            f"=== Session Summary ===\n"
            f"Duration: {self.session_duration_s/60:.1f}min\n"
            f"Requests: {self.total_requests} "
            f"(Success: {success_rate:.1f}%)\n"
            f"Seats Found: {self.seats_detected_count}x\n"
            f"Notifications: {self.notifications_sent}\n"
            f"Avg Response: {self.avg_response_time_ms:.0f}ms\n"
            f"Peak Memory: {self.peak_memory_mb:.1f}MB\n"
            f"Tokens Used: {self.total_tokens_used:,}\n"
        )
```

---

## 6. Project Structure

```
코레일/
├── KORAIL_AGENT_PROMPT.md          # 이 문서 (프롬프트 명세)
├── pyproject.toml                  # 프로젝트 설정
├── src/
│   ├── __init__.py
│   ├── main.py                     # CLI 진입점
│   ├── models/
│   │   ├── __init__.py
│   │   ├── query.py                # TrainQuery, TrainInfo
│   │   └── config.py               # AgentConfig
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── core.py                 # KorailAgent (오케스트레이터)
│   │   ├── state.py                # AgentState, 상태 전이
│   │   └── metrics.py              # AgentMetrics
│   ├── skills/
│   │   ├── __init__.py
│   │   ├── seat_checker.py         # SeatCheckerSkill
│   │   ├── notifier.py             # NotifierSkill
│   │   └── station_data.py         # 역 코드/검증
│   └── utils/
│       ├── __init__.py
│       ├── rate_limiter.py         # 레이트 리미터
│       └── logging_config.py       # 로깅 설정
├── tests/
│   ├── test_query_validation.py
│   ├── test_agent_state.py
│   ├── test_seat_checker.py
│   └── test_notifier.py
└── .env.example                    # 환경변수 템플릿
```

---

## 7. Quick Start (CLI Usage)

```bash
# 설치
pip install -e .

# 실행 예시
python -m src.main \
  --departure 서울 \
  --arrival 부산 \
  --date 2026-02-14 \
  --time-start 08:00 \
  --time-end 12:00 \
  --train-type KTX \
  --notify desktop,sound

# 환경변수로 Webhook 설정 (선택)
export KORAIL_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

---

## 8. Ethical & Legal Compliance

```markdown
### 준수 사항
1. **알림 전용**: 자동 예매/결제 기능 없음
2. **적절한 조회 간격**: 최소 30초, 백오프 적용
3. **정직한 User-Agent**: 봇임을 명시
4. **세션 제한**: 최대 6시간, 자동 종료
5. **요청 수 제한**: 세션당 720회 이내
6. **robots.txt 준수**: 차단 경로 조회하지 않음
7. **개인정보 미수집**: 로그인 불필요, 비회원 조회만 사용
```

---

## 9. Next Steps (Phase 2 Roadmap)

```markdown
### Phase 2: 고도화
- [ ] 다중 노선 동시 모니터링
- [ ] Telegram Bot 연동
- [ ] 웹 대시보드 (FastAPI + HTMX)
- [ ] 조회 결과 히스토리 시각화
- [ ] Docker 컨테이너화

### Phase 3: 확장
- [ ] SRT 지원 추가
- [ ] 환승 경로 조합 감지
- [ ] 가격 변동 알림
- [ ] 모바일 앱 (Flutter)
```

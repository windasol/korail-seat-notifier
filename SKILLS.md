# Korail Agent Skills Specification

> 각 에이전트가 사용하는 스킬의 상세 인터페이스, 구현 가이드, 테스트 명세

---

## 1. Skills Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    SKILL REGISTRY                            │
├──────────────┬───────────────────────────────────────────────┤
│ Agent        │ Skills                                        │
├──────────────┼───────────────────────────────────────────────┤
│ Input        │ ParserSkill, ValidationSkill, StationSkill    │
│ Monitor      │ SeatCheckerSkill, PollerSkill, RateLimiterSkill│
│ Notifier     │ DesktopSkill, SoundSkill, WebhookSkill,       │
│              │ TelegramSkill                                 │
│ Health       │ MetricsSkill, LoggerSkill, GCSkill            │
└──────────────┴───────────────────────────────────────────────┘
```

---

## 2. Input Agent Skills

### 2.1 ParserSkill

```
목적: 사용자 원시 입력을 구조화된 딕셔너리로 변환
위치: src/skills/parser.py
```

**인터페이스:**
```python
class ParserSkill:
    """입력 파싱 스킬"""

    def parse_cli(self, args: argparse.Namespace) -> dict:
        """CLI 인자 → dict 변환"""
        ...

    def parse_interactive(self, raw_inputs: dict[str, str]) -> dict:
        """대화형 입력 → dict 변환 (공백 정규화, 타입 변환)"""
        ...

    def parse_natural_language(self, text: str) -> dict:
        """자연어 → dict (Phase 2: LLM 기반 파싱)"""
        ...
```

**입출력 스키마:**
```python
# 입력 (raw)
{"departure": "서울역", "arrival": " 부산 ", "date": "2026-02-14", ...}

# 출력 (parsed)
{"departure": "서울", "arrival": "부산", "date": date(2026,2,14), ...}
```

**테스트 케이스:**
| 케이스 | 입력 | 예상 출력 |
|--------|------|-----------|
| 정상 CLI | `--departure 서울 --arrival 부산` | `{"departure":"서울", "arrival":"부산"}` |
| 공백 처리 | `"  서울역  "` | `"서울"` |
| 날짜 포맷 1 | `"2026-02-14"` | `date(2026,2,14)` |
| 날짜 포맷 2 | `"20260214"` | `date(2026,2,14)` |
| 시간 포맷 1 | `"08:00"` | `time(8,0)` |
| 시간 포맷 2 | `"0800"` | `time(8,0)` |

---

### 2.2 ValidationSkill

```
목적: 비즈니스 규칙에 따른 입력값 검증
위치: src/skills/validation.py
```

**인터페이스:**
```python
class ValidationSkill:
    """입력 검증 스킬"""

    def validate_query(self, data: dict) -> TrainQuery:
        """전체 검증 후 불변 TrainQuery 반환. 실패 시 ValueError."""
        ...

    def validate_date(self, d: date) -> None:
        """과거 날짜, 90일 이후 검증"""
        ...

    def validate_time_range(self, start: time, end: time) -> None:
        """시작 < 종료 검증"""
        ...

    def validate_passengers(self, count: int) -> None:
        """1~9명 범위 검증"""
        ...
```

**검증 규칙:**
```
R1: departure_station ∈ STATION_CODES
R2: arrival_station ∈ STATION_CODES
R3: departure_station ≠ arrival_station
R4: departure_date ≥ today
R5: departure_date ≤ today + 90일
R6: preferred_time_start < preferred_time_end
R7: 1 ≤ passenger_count ≤ 9
R8: train_type ∈ ["KTX", "KTX-산천", ...]
R9: seat_type ∈ ["일반실", "특실"]
```

**테스트 케이스:**
| 케이스 | 검증 규칙 | 입력 | 결과 |
|--------|-----------|------|------|
| 과거 날짜 | R4 | `2024-01-01` | `ValueError` |
| 먼 미래 | R5 | `2027-01-01` | `ValueError` |
| 동일 출도착 | R3 | 서울→서울 | `ValueError` |
| 승객 0명 | R7 | `count=0` | `ValueError` |
| 승객 10명 | R7 | `count=10` | `ValueError` |
| 시간 역전 | R6 | 12:00→08:00 | `ValueError` |
| 정상 | All | 서울→부산, 내일, 08~12 | `TrainQuery` |

---

### 2.3 StationSkill

```
목적: 역 이름 정규화 및 코드 매핑
위치: src/skills/station_data.py
```

**인터페이스:**
```python
# 상수
STATION_CODES: dict[str, str]    # {"서울": "0001", ...}
STATION_ALIASES: dict[str, str]  # {"서울역": "서울", "울산": "울산(통도사)", ...}

def validate_station(name: str) -> str:
    """역 이름 정규화. 별칭 → 정식 명칭. 미지원 역 → ValueError"""
    ...

def get_station_code(name: str) -> str:
    """정규화된 역 이름 → 코레일 역 코드"""
    ...
```

**지원 역 (17개 주요역):**
```
서울(0001), 용산(0015), 영등포(0020), 수원(0055),
천안아산(0502), 대전(0010), 동대구(0015), 부산(0020),
광주송정(0036), 목포(0041), 전주(0045), 익산(0030),
강릉(0115), 평창(0112), 여수엑스포(0049), 포항(0520),
울산(통도사)(0930), 진주(0056)
```

---

## 3. Monitor Agent Skills

### 3.1 SeatCheckerSkill

```
목적: 코레일 웹 페이지 조회 → 좌석 가용성 파싱
위치: src/skills/seat_checker.py
의존성: aiohttp
```

**인터페이스:**
```python
class SeatCheckerSkill:
    """코레일 좌석 조회"""

    _session: ClassVar[Optional[aiohttp.ClientSession]] = None

    async def check(self, query: TrainQuery) -> CheckResult:
        """좌석 가용성 조회"""
        ...

    @staticmethod
    def _build_params(query: TrainQuery) -> dict[str, str]:
        """API 요청 파라미터 구성"""
        ...

    @staticmethod
    def _parse_response(data: dict, query: TrainQuery) -> list[TrainInfo]:
        """응답 → TrainInfo 목록 (시간 범위 필터 적용)"""
        ...

    @classmethod
    async def close(cls) -> None:
        """커넥션 풀 정리"""
        ...
```

**요청 파라미터 매핑:**
```python
{
    "txtGoStart": query.departure_station,     # 출발역 이름
    "txtGoEnd": query.arrival_station,          # 도착역 이름
    "txtGoAbrdDt": "YYYYMMDD",                 # 출발 날짜
    "txtGoHour": "HHMMSS",                     # 출발 시간
    "selGoTrain": "100",                        # 열차 종류 코드
    "txtSeatAttCd": "015",                      # 좌석 속성
    "txtPsgFlg_1": str(passenger_count),        # 일반 승객 수
}
```

**열차 종류 코드 매핑:**
```python
TRAIN_TYPE_CODES = {
    "KTX": "100", "KTX-산천": "100", "KTX-이음": "100",
    "ITX-새마을": "101", "ITX-청춘": "109", "무궁화": "102",
    "전체": "109",
}
```

**응답 파싱 규칙:**
```python
좌석 상태 → 숫자 변환:
  "매진"      → 0
  "없음"      → 0
  "예약대기"  → 0
  "가능"      → 99 (좌석 수 미공개 시)
  "충분"      → 99
  "5석"       → 5
  "잔여 12석" → 12
```

**테스트 케이스:**
| 함수 | 입력 | 예상 |
|------|------|------|
| `_parse_time("083000")` | 6자리 문자열 | `time(8,30)` |
| `_parse_seat_count("매진")` | 매진 문자열 | `0` |
| `_parse_seat_count("가능")` | 가능 문자열 | `99` |
| `_parse_seat_count("잔여 12석")` | 숫자 포함 | `12` |
| `_calc_duration(8:00, 10:30)` | 정상 범위 | `150분` |
| `_calc_duration(23:00, 1:00)` | 자정 교차 | `1320분` |
| `_build_params(query)` | KTX, 서울→부산 | 코드 100, 역명 매핑 |
| `_parse_response({}, q)` | 빈 응답 | `[]` |
| `_parse_response(data, q)` | 시간 범위 외 열차 | 필터링 |

---

### 3.2 PollerSkill

```
목적: 적응형 폴링 간격 계산 (지수 백오프 + 지터)
위치: src/skills/poller.py
```

**인터페이스:**
```python
class PollerSkill:
    """적응형 폴링 스케줄러"""

    def __init__(
        self,
        base_interval: float = 30.0,
        max_interval: float = 300.0,
        backoff_multiplier: float = 1.5,
        jitter_range: float = 5.0,
    ) -> None: ...

    def next_interval(self, had_error: bool) -> float:
        """다음 폴링까지 대기 시간 계산 (초)"""
        ...

    def reset(self) -> None:
        """간격을 base_interval로 리셋"""
        ...
```

**알고리즘:**
```
에러 시:
  current = min(current × backoff_multiplier, max_interval)

성공 시:
  current = max(current ÷ 1.2, base_interval)

최종:
  return current + random(0, jitter_range)
```

**테스트 케이스:**
| 시나리오 | 상태 | 예상 간격 범위 |
|----------|------|---------------|
| 초기 | 성공 | 30~35초 |
| 1회 에러 | 에러 | 45~50초 |
| 2회 연속 에러 | 에러 | 67.5~72.5초 |
| 에러 후 성공 | 성공 | 37.5~62.5초 (감소 중) |
| 최대 백오프 | 10회 에러 | 300~305초 (상한) |

---

### 3.3 RateLimiterSkill

```
목적: 토큰 버킷 알고리즘으로 요청 속도 제한
위치: src/utils/rate_limiter.py
```

**인터페이스:**
```python
class TokenBucketRateLimiter:
    """토큰 버킷 레이트 리미터"""

    def __init__(
        self,
        rate: float = 1/30,   # 초당 허용 요청 수
        burst: int = 1,        # 버스트 허용 수
    ) -> None: ...

    async def acquire(self) -> float:
        """토큰 1개 소비. 대기한 시간(초) 반환."""
        ...
```

**동작 원리:**
```
초기 토큰: burst (1)
토큰 충전: 경과 시간 × rate
소비: 토큰 ≥ 1 → 즉시 소비, < 1 → 대기

예시 (rate=1/30, burst=1):
- t=0s  : 토큰=1, 즉시 소비 → 0
- t=10s : 토큰=0.33, 대기 20s
- t=30s : 토큰=1.0, 즉시 소비
```

---

## 4. Notifier Agent Skills

### 4.1 DesktopNotifySkill

```
목적: OS별 네이티브 데스크톱 알림 표시
위치: src/skills/notifier.py (내장)
플랫폼: Windows, macOS, Linux
```

**플랫폼별 구현:**
```
Windows:
  1순위: winotify (Toast Notification)
  2순위: PowerShell NotifyIcon (fallback)

macOS:
  osascript display notification

Linux:
  notify-send (libnotify)
```

**알림 포맷:**
```
┌──────────────────────────────────────┐
│ 코레일 빈자리 발견!                    │
│                                       │
│  KTX 101호 09:00→11:30 (일반 5석)     │
│  KTX 105호 10:00→12:30 (특실 2석)     │
└──────────────────────────────────────┘
```

---

### 4.2 SoundNotifySkill

```
목적: 알림음 재생
위치: src/skills/notifier.py (내장)
```

**구현:**
```
Windows: winsound.Beep(1000Hz, 500ms) × 3회
기타:    터미널 벨 (\a) × 3회
```

---

### 4.3 WebhookSkill

```
목적: 외부 서비스 (Slack/Discord) HTTP POST 알림
위치: src/skills/notifier.py (내장)
설정: KORAIL_WEBHOOK_URL 환경변수
```

**페이로드:**
```json
{
  "text": "*코레일 빈자리 발견!*\n  KTX 101호 09:00→11:30 (일반 5석)"
}
```

**타임아웃:** 10초

---

### 4.4 TelegramSkill (Phase 2)

```
목적: Telegram Bot API 알림 발송
위치: src/skills/telegram.py (예정)
설정: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
```

**인터페이스 (예정):**
```python
class TelegramSkill:
    async def send(self, payload: NotificationPayload) -> bool:
        """Telegram 메시지 발송"""
        ...
```

---

## 5. Health Agent Skills

### 5.1 MetricsSkill

```
목적: 런타임 메트릭 집계
위치: src/agent/metrics.py
```

**수집 메트릭:**
```python
@dataclass
class AgentMetrics:
    total_requests: int         # 총 요청 수
    successful_checks: int      # 성공 조회 수
    failed_checks: int          # 실패 조회 수
    seats_detected_count: int   # 좌석 감지 횟수
    notifications_sent: int     # 알림 발송 횟수
    avg_response_time_ms: float # 평균 응답 시간
    peak_memory_mb: float       # 최대 메모리 사용
    session_duration_s: float   # 세션 경과 시간

    def summary(self) -> str:
        """세션 종료 리포트 문자열"""
        ...

    def record_request(self, success: bool, elapsed_ms: float) -> None:
        """요청 기록"""
        ...

    def record_detection(self) -> None: ...
    def record_notification(self) -> None: ...
    def update_memory(self) -> None: ...
```

---

### 5.2 LoggerSkill

```
목적: 구조화 로깅 (콘솔 컬러 + 파일)
위치: src/utils/logging_config.py
```

**기능:**
```
콘솔:
  - ANSI 컬러 (DEBUG=Cyan, INFO=Green, WARNING=Yellow, ERROR=Red)
  - 포맷: "HH:MM:SS LEVEL    name │ message"

파일 (선택):
  - UTF-8 인코딩
  - 포맷: "YYYY-MM-DD HH:MM:SS [LEVEL] name: message"

Windows:
  - ANSI escape 자동 활성화 (VT Processing)
```

---

### 5.3 GCSkill

```
목적: 메모리 관리 및 가비지 컬렉션
위치: Agent core 내장
```

**트리거 조건:**
```
요청 50회마다 → gc.collect(generation=0)
로그 버퍼 초과 → ring buffer 절반 제거
세션 종료 → 커넥션 풀 close
```

---

## 6. Skill Interface Contract

모든 스킬은 다음 계약을 준수합니다:

```python
from abc import ABC, abstractmethod
from typing import TypeVar, Generic

T_In = TypeVar("T_In")
T_Out = TypeVar("T_Out")

class BaseSkill(ABC, Generic[T_In, T_Out]):
    """스킬 기본 인터페이스"""

    @property
    @abstractmethod
    def name(self) -> str:
        """스킬 고유 이름"""

    @abstractmethod
    async def execute(self, input_data: T_In) -> T_Out:
        """스킬 실행"""

    async def setup(self) -> None:
        """초기화 (선택)"""

    async def teardown(self) -> None:
        """정리 (선택)"""
```

**규칙:**
1. 스킬은 **단일 책임**: 하나의 명확한 작업만 수행
2. 스킬은 **상태 비공유**: 에이전트를 통해서만 데이터 전달
3. 스킬은 **실패 격리**: 개별 스킬 실패가 다른 스킬에 영향 없음
4. 스킬은 **테스트 가능**: 모든 스킬에 단위 테스트 필수

---

## 7. Skill Dependencies Map

```
ParserSkill
  └── (없음)

ValidationSkill
  └── StationSkill (역 검증 위임)

StationSkill
  └── (없음, 정적 데이터)

SeatCheckerSkill
  └── aiohttp (HTTP 클라이언트)

PollerSkill
  └── (없음, 순수 계산)

RateLimiterSkill
  └── asyncio (sleep)

DesktopNotifySkill
  ├── winotify (Windows, 선택)
  └── subprocess (OS 명령)

SoundNotifySkill
  └── winsound (Windows) / 터미널 벨

WebhookSkill
  └── aiohttp

TelegramSkill
  └── aiohttp

MetricsSkill
  └── psutil (메모리 측정, 선택)

LoggerSkill
  └── logging (표준 라이브러리)

GCSkill
  └── gc (표준 라이브러리)
```

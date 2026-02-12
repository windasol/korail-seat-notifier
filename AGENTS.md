# Korail Agent System Architecture

> **Version**: 2.0.0
> **Type**: Multi-Agent Orchestration System
> **Purpose**: 코레일 좌석 빈자리 감지 → 알림 → 확장 가능한 에이전트 파이프라인

---

## 1. Agent Overview Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR AGENT                          │
│            (총괄 오케스트레이터 - 모든 에이전트 조율)                    │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ INPUT    │  │ MONITOR  │  │ NOTIFIER │  │ HEALTH   │           │
│  │ AGENT    │→→│ AGENT    │→→│ AGENT    │  │ AGENT    │           │
│  │          │  │          │  │          │  │ (감시)    │           │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
│       │              │              │              │                │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Parser  │  │ Poller   │  │ Desktop  │  │ Metrics  │           │
│  │ Skill   │  │ Skill    │  │ Skill    │  │ Skill    │           │
│  │ Valid.  │  │ Seat     │  │ Sound    │  │ Logger   │           │
│  │ Skill   │  │ Checker  │  │ Webhook  │  │ Skill    │           │
│  │ Station │  │ Skill    │  │ Skill    │  │ GC       │           │
│  │ Skill   │  │ Rate     │  │ Telegram │  │ Skill    │           │
│  └─────────┘  │ Limiter  │  │ Skill    │  └──────────┘           │
│               │ Skill    │  └──────────┘                          │
│               └──────────┘                                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Agent Definitions

### 2.1 Orchestrator Agent (총괄 오케스트레이터)

| 항목 | 설명 |
|------|------|
| **ID** | `orchestrator` |
| **역할** | 전체 파이프라인 제어, 에이전트 생명주기 관리, 에러 복구 |
| **입력** | `TrainQuery` (사용자 검색 요청) |
| **출력** | 세션 종료 리포트 (`AgentMetrics`) |
| **상태** | `IDLE → RUNNING → STOPPING → STOPPED` |

```
책임:
├── 에이전트 초기화 & 의존성 주입
├── Input Agent → Monitor Agent → Notifier Agent 파이프라인 조율
├── Health Agent로부터 메트릭 수집
├── 글로벌 에러 핸들링 & 복구 전략
├── Graceful Shutdown (Ctrl+C, 시간 초과, 에러 한계)
└── 세션 종료 리포트 생성
```

**핵심 규칙:**
- 단일 세션 = 단일 Orchestrator 인스턴스
- 모든 에이전트 간 통신은 Orchestrator를 경유
- 에이전트 실패 시 격리 & 재시작 (Circuit Breaker 패턴)

---

### 2.2 Input Agent (입력 처리 에이전트)

| 항목 | 설명 |
|------|------|
| **ID** | `input_agent` |
| **역할** | 사용자 입력 수신, 파싱, 검증, 정규화 |
| **입력** | CLI args / 대화형 입력 (raw string) |
| **출력** | 검증된 `TrainQuery` 객체 |
| **상태** | Stateless (요청-응답) |

```
스킬 구성:
├── ParserSkill       : 자연어/CLI → 구조화 데이터 변환
├── ValidationSkill   : 비즈니스 규칙 검증 (날짜, 시간, 승객 수)
└── StationSkill      : 역 이름 정규화 & 코드 매핑
```

**입력 플로우:**
```
[Raw Input]
    │
    ├── CLI Mode ──────► argparse 파싱 ──► 구조화
    │
    └── Interactive Mode ► 대화형 프롬프트 ──► 구조화
                                │
                          ┌─────▼─────┐
                          │ ParserSkill│
                          └─────┬─────┘
                                │
                          ┌─────▼──────────┐
                          │ StationSkill   │ 역 이름 → 코드 변환
                          └─────┬──────────┘
                                │
                          ┌─────▼──────────────┐
                          │ ValidationSkill    │ 규칙 검증
                          └─────┬──────────────┘
                                │
                          ┌─────▼─────┐
                          │ TrainQuery│ (불변 객체)
                          └───────────┘
```

---

### 2.3 Monitor Agent (모니터링 에이전트)

| 항목 | 설명 |
|------|------|
| **ID** | `monitor_agent` |
| **역할** | 주기적 좌석 조회, 가용성 판별, 폴링 전략 관리 |
| **입력** | `TrainQuery` |
| **출력** | `CheckResult` (조회 결과) → Event emit |
| **상태** | `IDLE → POLLING → DETECTED → IDLE` (루프) |

```
스킬 구성:
├── SeatCheckerSkill    : 코레일 API 호출 & 응답 파싱
├── PollerSkill         : 적응형 폴링 간격 계산 (백오프 + 지터)
└── RateLimiterSkill    : 토큰 버킷 기반 요청 속도 제한
```

**상태 머신:**
```
┌──────┐    poll()    ┌──────────┐   found    ┌──────────┐
│ IDLE │───────────►│ POLLING  │──────────►│ DETECTED │
└──────┘            └────┬─────┘            └─────┬────┘
    ▲                    │ not found              │ emit event
    │                    │                        │
    └────────────────────┘                        │
    ▲                                             │
    └─────────────────────────────────────────────┘
```

**적응형 폴링 전략:**
```python
# 정상 상태: base_interval (30s)
# 에러 발생: interval × backoff_multiplier (1.5x), max 300s
# 에러 복구: interval ÷ 1.2, min base_interval
# 지터: 0~5s 랜덤 추가 (서버 부하 분산)

interval_formula = min(
    base × (backoff ^ error_count) + random(0, jitter),
    max_interval
)
```

---

### 2.4 Notifier Agent (알림 에이전트)

| 항목 | 설명 |
|------|------|
| **ID** | `notifier_agent` |
| **역할** | 좌석 감지 이벤트 수신 → 다채널 알림 발송 |
| **입력** | `CheckResult` (가용 좌석 정보) |
| **출력** | 알림 발송 결과 (성공/실패) |
| **상태** | `IDLE → SENDING → COOLDOWN → IDLE` |

```
스킬 구성:
├── DesktopNotifySkill  : OS별 데스크톱 알림 (Win/Mac/Linux)
├── SoundNotifySkill    : 비프음/커스텀 사운드 재생
├── WebhookSkill        : Slack/Discord/커스텀 Webhook
└── TelegramSkill       : Telegram Bot API (Phase 2)
```

**알림 쿨다운:**
```
[DETECTED event]
    │
    ├── 마지막 알림 후 60초 경과? ──► No ──► 스킵
    │
    └── Yes
         │
         ├── DesktopNotifySkill  ──►  OS 알림
         ├── SoundNotifySkill    ──►  비프음 3회
         └── WebhookSkill        ──►  HTTP POST
         │
         └── (모두 병렬 실행, 개별 실패 격리)
```

---

### 2.5 Health Agent (상태 감시 에이전트)

| 항목 | 설명 |
|------|------|
| **ID** | `health_agent` |
| **역할** | 시스템 메트릭 수집, 리소스 제한 감시, 자동 복구 |
| **입력** | 에이전트 런타임 메트릭 |
| **출력** | 상태 리포트, 경고/중지 신호 |
| **상태** | `WATCHING` (항상 활성) |

```
스킬 구성:
├── MetricsSkill   : 요청 수, 성공률, 응답 시간 집계
├── LoggerSkill    : 구조화 로깅 (ring buffer, 파일)
└── GCSkill        : 메모리 감시 & 가비지 컬렉션 트리거
```

**감시 항목:**
```
리소스 제한:
├── 세션 시간        : max 6시간 → STOP 신호
├── 요청 수          : max 720회/세션 → STOP 신호
├── 연속 에러        : max 10회 → STOP 신호
├── 메모리 사용량    : max 50MB RSS → GC 트리거
└── 응답 지연        : avg > 10s → 경고 로그
```

---

## 3. Agent Communication Protocol

### 3.1 이벤트 기반 통신

```python
# 에이전트 간 이벤트 타입
class AgentEvent:
    QUERY_READY       = "query.ready"        # Input → Orchestrator
    POLL_START        = "poll.start"          # Orchestrator → Monitor
    POLL_RESULT       = "poll.result"         # Monitor → Orchestrator
    SEAT_DETECTED     = "seat.detected"       # Monitor → Orchestrator
    NOTIFY_REQUEST    = "notify.request"      # Orchestrator → Notifier
    NOTIFY_COMPLETE   = "notify.complete"     # Notifier → Orchestrator
    HEALTH_WARNING    = "health.warning"      # Health → Orchestrator
    HEALTH_CRITICAL   = "health.critical"     # Health → Orchestrator
    SESSION_STOP      = "session.stop"        # Orchestrator → All
```

### 3.2 메시지 포맷

```python
@dataclass(frozen=True, slots=True)
class AgentMessage:
    event: str          # AgentEvent 값
    source: str         # 발신 에이전트 ID
    target: str         # 수신 에이전트 ID ("*" = broadcast)
    payload: Any        # 이벤트별 데이터
    timestamp: float    # monotonic() 시각
```

---

## 4. Agent Lifecycle

```
┌─────────────────────────────────────────────────┐
│              Agent Lifecycle                     │
│                                                  │
│  INIT ──► READY ──► ACTIVE ──► DRAINING ──► OFF │
│             │                      ▲              │
│             │        error         │              │
│             └──► RECOVERING ───────┘              │
│                                                  │
└─────────────────────────────────────────────────┘

INIT       : 의존성 주입, 설정 로드
READY      : 초기화 완료, 이벤트 대기
ACTIVE     : 이벤트 처리 중
DRAINING   : 진행 중인 작업 완료 대기 (graceful)
RECOVERING : 에러 복구 중 (재시도/재초기화)
OFF        : 종료
```

---

## 5. Error Handling Strategy

### 5.1 에이전트별 에러 격리

| 에이전트 | 에러 전략 | 한계 초과 시 |
|----------|-----------|-------------|
| Input Agent | 즉시 재입력 요청 | 세션 종료 |
| Monitor Agent | 지수 백오프 재시도 | Orchestrator에 CRITICAL 전달 |
| Notifier Agent | 채널별 독립 실패 격리 | 로그만 기록 (모니터링 계속) |
| Health Agent | 자체 복구 불가 → 로그 | Orchestrator 직접 중지 |

### 5.2 Circuit Breaker 패턴

```
         ┌──────────┐
         │  CLOSED   │  (정상 운영)
         └────┬──────┘
              │ 연속 에러 N회
              ▼
         ┌──────────┐
         │   OPEN    │  (요청 차단, 대기)
         └────┬──────┘
              │ timeout 후
              ▼
         ┌──────────┐
         │HALF-OPEN │  (시험 요청 1회)
         └────┬──────┘
              │
         성공? ──► CLOSED
         실패? ──► OPEN
```

---

## 6. Configuration Hierarchy

```yaml
# 설정 우선순위: CLI args > 환경변수 > config.yaml > 기본값

orchestrator:
  max_session_duration: 21600    # 6시간
  graceful_shutdown_timeout: 10  # 초

input_agent:
  supported_train_types:
    - KTX
    - KTX-산천
    - KTX-이음
    - ITX-새마을
    - ITX-청춘
    - 무궁화

monitor_agent:
  base_interval: 30
  max_interval: 300
  backoff_multiplier: 1.5
  jitter_range: 5.0
  max_requests_per_session: 720

notifier_agent:
  methods: [desktop, sound]
  cooldown: 60
  webhook_url: ${KORAIL_WEBHOOK_URL}

health_agent:
  max_consecutive_errors: 10
  max_memory_mb: 50
  gc_interval: 50
  log_max_entries: 100
```

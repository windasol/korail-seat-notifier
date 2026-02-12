# Korail Development Pipeline

> 개발 단계별 구현 순서, 작업 명세, 테스트 전략, 배포 파이프라인

---

## 1. Pipeline Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    DEVELOPMENT PIPELINE                          │
│                                                                  │
│  Phase 1        Phase 2        Phase 3        Phase 4            │
│  Foundation     Core Agents    Integration    Polish & Deploy    │
│  ──────────     ──────────     ──────────     ──────────────     │
│  프로젝트 셋업   에이전트 구현   통합 & E2E     최적화 & 배포      │
│  모델 확정       스킬 구현       에러 처리      Docker/CI          │
│  테스트 인프라   단위 테스트     부하 테스트    문서화              │
│                                                                  │
│  [1주차]        [2~3주차]      [4주차]        [5주차]            │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Phase 1: Foundation (프로젝트 기반)

### 2.1 프로젝트 구조 확정

```
코레일/
├── pyproject.toml                  # 빌드 & 의존성 관리
├── .env.example                    # 환경변수 템플릿
├── .gitignore
├── AGENTS.md                       # 에이전트 아키텍처
├── SKILLS.md                       # 스킬 명세
├── PIPELINE.md                     # 이 문서
├── KORAIL_AGENT_PROMPT.md          # 원본 프롬프트
├── CLAUDE.md                       # Claude Code 프로젝트 설정
│
├── src/
│   ├── __init__.py
│   ├── main.py                     # CLI 진입점
│   │
│   ├── models/                     # 데이터 모델 (불변 객체)
│   │   ├── __init__.py
│   │   ├── query.py                # TrainQuery, TrainInfo, CheckResult
│   │   ├── config.py               # AgentConfig
│   │   └── events.py               # AgentEvent, AgentMessage
│   │
│   ├── agents/                     # 에이전트 레이어
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseAgent (추상 클래스)
│   │   ├── orchestrator.py         # OrchestratorAgent
│   │   ├── input_agent.py          # InputAgent
│   │   ├── monitor_agent.py        # MonitorAgent
│   │   ├── notifier_agent.py       # NotifierAgent
│   │   └── health_agent.py         # HealthAgent
│   │
│   ├── skills/                     # 스킬 레이어
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseSkill (추상 클래스)
│   │   ├── parser.py               # ParserSkill
│   │   ├── validation.py           # ValidationSkill
│   │   ├── station_data.py         # StationSkill (역 코드/검증)
│   │   ├── seat_checker.py         # SeatCheckerSkill
│   │   ├── poller.py               # PollerSkill
│   │   ├── notifier.py             # Notifier Skills (Desktop/Sound/Webhook)
│   │   └── telegram.py             # TelegramSkill (Phase 2 Extension)
│   │
│   ├── agent/                      # 레거시 호환 (기존 core.py)
│   │   ├── __init__.py
│   │   ├── core.py                 # KorailAgent (현재 구현)
│   │   ├── state.py                # AgentState, validate_transition
│   │   └── metrics.py              # AgentMetrics
│   │
│   └── utils/                      # 유틸리티
│       ├── __init__.py
│       ├── rate_limiter.py         # TokenBucketRateLimiter
│       └── logging_config.py       # 로깅 설정
│
├── tests/
│   ├── conftest.py                 # pytest fixtures
│   ├── unit/                       # 단위 테스트
│   │   ├── test_query_validation.py
│   │   ├── test_agent_state.py
│   │   ├── test_seat_checker.py
│   │   ├── test_poller.py
│   │   ├── test_rate_limiter.py
│   │   ├── test_notifier.py
│   │   ├── test_parser.py
│   │   └── test_station_data.py
│   ├── integration/                # 통합 테스트
│   │   ├── test_monitor_flow.py
│   │   ├── test_notify_flow.py
│   │   └── test_orchestrator.py
│   └── e2e/                        # E2E 테스트
│       └── test_full_pipeline.py
│
└── docker/                         # Docker (Phase 4)
    ├── Dockerfile
    └── docker-compose.yml
```

### 2.2 Task Checklist - Phase 1

```
[P1-01] pyproject.toml 작성
  ├── 의존성: aiohttp, winotify (win), psutil
  ├── 개발 의존성: pytest, pytest-asyncio, ruff, mypy
  ├── scripts: korail = "src.main:cli_entry"
  └── pytest 설정, ruff 설정

[P1-02] 데이터 모델 확정 (src/models/)
  ├── query.py: TrainQuery, TrainInfo, CheckResult
  ├── config.py: AgentConfig
  └── events.py: AgentEvent, AgentMessage

[P1-03] 스킬 기본 인터페이스 (src/skills/base.py)
  └── BaseSkill[T_In, T_Out] 추상 클래스

[P1-04] 에이전트 기본 인터페이스 (src/agents/base.py)
  └── BaseAgent 추상 클래스 (lifecycle: setup/run/teardown)

[P1-05] 테스트 인프라 구성
  ├── conftest.py: 공통 fixtures (mock_query, mock_config)
  ├── pytest.ini 또는 pyproject.toml [tool.pytest]
  └── 기존 테스트 3개 그린 확인

[P1-06] 린터 & 타입체커 설정
  ├── ruff.toml (또는 pyproject.toml 내)
  └── mypy 설정 (strict mode)
```

---

## 3. Phase 2: Core Implementation (핵심 구현)

### 3.1 구현 순서 (의존성 기반)

```
Layer 1 - Skills (의존성 없음, 독립 테스트 가능)
  ├── [P2-01] StationSkill ──────── (정적 데이터, 이미 구현됨)
  ├── [P2-02] ParserSkill ───────── (입력 → dict)
  ├── [P2-03] ValidationSkill ──── (dict → TrainQuery)
  ├── [P2-04] PollerSkill ───────── (간격 계산)
  ├── [P2-05] RateLimiterSkill ─── (이미 구현됨)
  ├── [P2-06] SeatCheckerSkill ─── (이미 구현됨, 리팩토링)
  └── [P2-07] NotifierSkills ───── (이미 구현됨, 분리)

Layer 2 - Agents (Skills 의존)
  ├── [P2-08] InputAgent ─────────── (Parser + Validation + Station)
  ├── [P2-09] MonitorAgent ──────── (SeatChecker + Poller + RateLimiter)
  ├── [P2-10] NotifierAgent ─────── (Desktop + Sound + Webhook)
  └── [P2-11] HealthAgent ──────── (Metrics + Logger + GC)

Layer 3 - Orchestrator (Agents 의존)
  └── [P2-12] OrchestratorAgent ─── (전체 조율)
```

### 3.2 Task Checklist - Phase 2

```
[P2-01] StationSkill 검증 (기존 코드 확인)
  ├── validate_station() 동작 확인
  ├── 별칭 매핑 (서울역→서울) 확인
  └── test_station_data.py 그린 확인

[P2-02] ParserSkill 구현
  ├── src/skills/parser.py
  ├── parse_cli(), parse_interactive()
  ├── 공백/포맷 정규화
  └── tests/unit/test_parser.py

[P2-03] ValidationSkill 구현
  ├── src/skills/validation.py
  ├── validate_query() → TrainQuery 반환
  ├── 비즈니스 규칙 9개 검증
  └── tests/unit/test_validation.py (기존 test_query_validation 확장)

[P2-04] PollerSkill 구현
  ├── src/skills/poller.py
  ├── next_interval(had_error) → float
  ├── 백오프 + 지터 + 복구 로직
  └── tests/unit/test_poller.py

[P2-05] RateLimiterSkill 검증 (기존 코드)
  ├── TokenBucketRateLimiter 동작 확인
  └── tests/unit/test_rate_limiter.py

[P2-06] SeatCheckerSkill 리팩토링
  ├── BaseSkill 인터페이스 적용
  ├── 에러 분류 (네트워크/파싱/서버)
  └── tests/unit/test_seat_checker.py 확장

[P2-07] NotifierSkills 분리
  ├── DesktopNotifySkill, SoundNotifySkill, WebhookSkill 분리
  ├── 각각 독립 실행 가능하도록
  └── tests/unit/test_notifier.py (각 스킬별)

[P2-08] InputAgent 구현
  ├── src/agents/input_agent.py
  ├── ParserSkill + ValidationSkill + StationSkill 조합
  ├── process(raw_input) → TrainQuery
  └── tests/unit/test_input_agent.py

[P2-09] MonitorAgent 구현
  ├── src/agents/monitor_agent.py
  ├── SeatCheckerSkill + PollerSkill + RateLimiterSkill 조합
  ├── 상태 머신: IDLE → POLLING → DETECTED → IDLE
  └── tests/unit/test_monitor_agent.py

[P2-10] NotifierAgent 구현
  ├── src/agents/notifier_agent.py
  ├── 다채널 병렬 발송, 개별 실패 격리
  ├── 쿨다운 관리
  └── tests/unit/test_notifier_agent.py

[P2-11] HealthAgent 구현
  ├── src/agents/health_agent.py
  ├── MetricsSkill + LoggerSkill + GCSkill
  ├── 리소스 한계 감시, 경고/중지 신호
  └── tests/unit/test_health_agent.py

[P2-12] OrchestratorAgent 구현
  ├── src/agents/orchestrator.py
  ├── Input → Monitor → Notifier 파이프라인
  ├── Health Agent 통합, 이벤트 기반 통신
  ├── Graceful Shutdown
  └── tests/unit/test_orchestrator.py
```

---

## 4. Phase 3: Integration & Testing (통합)

### 4.1 Task Checklist - Phase 3

```
[P3-01] 통합 테스트: 모니터링 플로우
  ├── tests/integration/test_monitor_flow.py
  ├── Mock API → MonitorAgent → CheckResult 검증
  └── 에러 백오프, 재시도 시나리오

[P3-02] 통합 테스트: 알림 플로우
  ├── tests/integration/test_notify_flow.py
  ├── DETECTED 이벤트 → NotifierAgent → 알림 발송 검증
  └── 쿨다운, 실패 격리 시나리오

[P3-03] 통합 테스트: 오케스트레이터
  ├── tests/integration/test_orchestrator.py
  ├── 전체 파이프라인 (Input → Monitor → Notifier)
  ├── Graceful Shutdown 시나리오
  └── 리소스 한계 초과 시나리오

[P3-04] E2E 테스트
  ├── tests/e2e/test_full_pipeline.py
  ├── CLI 입력 → 모니터링 시작 → 좌석 감지 → 알림 (mocked)
  └── 세션 종료 리포트 검증

[P3-05] 에러 핸들링 강화
  ├── Circuit Breaker 패턴 적용
  ├── 에이전트별 에러 격리 검증
  ├── 네트워크 에러, 타임아웃, 파싱 에러 분류
  └── 에러별 복구 전략 구현

[P3-06] 성능 테스트
  ├── 6시간 세션 시뮬레이션 (시간 가속)
  ├── 메모리 사용량 프로파일링 (< 50MB)
  ├── 응답 시간 벤치마크
  └── 동시 다중 쿼리 시나리오 (Phase 2 준비)
```

---

## 5. Phase 4: Polish & Deploy (최적화 & 배포)

### 5.1 Task Checklist - Phase 4

```
[P4-01] main.py 업데이트
  ├── OrchestratorAgent 기반으로 전환
  ├── 기존 KorailAgent와 호환 유지
  └── CLI 인터페이스 확장 (config 파일 지원)

[P4-02] pyproject.toml 최종화
  ├── 의존성 정리
  ├── optional-dependencies: [dev], [telegram]
  └── 버전 범핑 (2.0.0)

[P4-03] Docker 구성
  ├── docker/Dockerfile (multi-stage)
  ├── docker/docker-compose.yml
  └── .dockerignore

[P4-04] CI/CD 파이프라인 (GitHub Actions)
  ├── .github/workflows/ci.yml
  ├── lint (ruff) → typecheck (mypy) → test (pytest) → build
  └── 커버리지 리포트

[P4-05] .env.example 업데이트
  ├── KORAIL_WEBHOOK_URL
  ├── TELEGRAM_BOT_TOKEN
  ├── TELEGRAM_CHAT_ID
  └── LOG_LEVEL, LOG_FILE
```

---

## 6. CI/CD Pipeline Design

### 6.1 GitHub Actions Workflow

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff
      - run: ruff check src/ tests/
      - run: ruff format --check src/ tests/

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: mypy src/

  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
        python: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -v --tb=short --cov=src --cov-report=xml
      - uses: codecov/codecov-action@v4
        if: matrix.os == 'ubuntu-latest' && matrix.python == '3.12'

  build:
    needs: [lint, typecheck, test]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build
      - run: python -m build
```

### 6.2 Local Development Commands

```bash
# 프로젝트 설치 (개발 모드)
pip install -e ".[dev]"

# 린트
ruff check src/ tests/
ruff format src/ tests/

# 타입 체크
mypy src/

# 테스트 (전체)
pytest tests/ -v

# 테스트 (단위만)
pytest tests/unit/ -v

# 테스트 (통합만)
pytest tests/integration/ -v

# 테스트 (커버리지)
pytest tests/ --cov=src --cov-report=html

# 실행
python -m src.main -d 서울 -a 부산 --date 2026-02-14 \
    --time-start 08:00 --time-end 12:00

# Docker
docker build -f docker/Dockerfile -t korail-notifier .
docker run --env-file .env korail-notifier \
    -d 서울 -a 부산 --date 2026-02-14 \
    --time-start 08:00 --time-end 12:00
```

---

## 7. Testing Strategy

### 7.1 테스트 피라미드

```
        ╱ E2E ╲                    ← 적음 (1~2개)
       ╱────────╲
      ╱Integration╲               ← 중간 (5~10개)
     ╱──────────────╲
    ╱   Unit Tests   ╲            ← 많음 (30~50개)
   ╱──────────────────╲
```

### 7.2 테스트 매트릭스

| 레이어 | 대상 | 테스트 수 (목표) | Mock 범위 |
|--------|------|-----------------|-----------|
| Unit - Skills | ParserSkill | 6 | 없음 (순수 함수) |
| Unit - Skills | ValidationSkill | 9 | StationSkill |
| Unit - Skills | StationSkill | 6 | 없음 (정적 데이터) |
| Unit - Skills | SeatCheckerSkill | 12 | aiohttp (응답 mock) |
| Unit - Skills | PollerSkill | 5 | 없음 (순수 계산) |
| Unit - Skills | RateLimiterSkill | 4 | asyncio.sleep |
| Unit - Skills | NotifierSkills | 6 | subprocess, winsound |
| Unit - Agents | InputAgent | 5 | Skills |
| Unit - Agents | MonitorAgent | 8 | SeatCheckerSkill |
| Unit - Agents | NotifierAgent | 6 | NotifierSkills |
| Unit - Agents | HealthAgent | 4 | 없음 |
| Integration | Monitor Flow | 3 | API 응답 |
| Integration | Notify Flow | 3 | OS 알림 |
| Integration | Orchestrator | 4 | API + 알림 |
| E2E | Full Pipeline | 2 | API + 알림 |
| **합계** | | **~83** | |

### 7.3 Mock/Fixture 전략

```python
# tests/conftest.py

@pytest.fixture
def sample_query() -> TrainQuery:
    return TrainQuery(
        departure_station="서울",
        arrival_station="부산",
        departure_date=date(2026, 3, 1),
        preferred_time_start=time(8, 0),
        preferred_time_end=time(12, 0),
    )

@pytest.fixture
def sample_config() -> AgentConfig:
    return AgentConfig(
        base_interval=1.0,  # 테스트용 빠른 간격
        max_interval=5.0,
        max_session_duration=10.0,
        max_requests_per_session=5,
    )

@pytest.fixture
def mock_api_response() -> dict:
    """코레일 API 정상 응답 mock"""
    return {
        "trn_infos": {
            "trn_info": [
                {
                    "h_trn_no": "101",
                    "h_trn_clsf_nm": "KTX",
                    "h_dpt_tm": "090000",
                    "h_arv_tm": "113000",
                    "h_rsv_psb_nm": "가능",
                    "h_spe_rsv_psb_nm": "매진",
                },
            ],
        },
    }

@pytest.fixture
def mock_empty_response() -> dict:
    """빈 좌석 없음 응답"""
    return {
        "trn_infos": {
            "trn_info": [
                {
                    "h_trn_no": "101",
                    "h_trn_clsf_nm": "KTX",
                    "h_dpt_tm": "090000",
                    "h_arv_tm": "113000",
                    "h_rsv_psb_nm": "매진",
                    "h_spe_rsv_psb_nm": "매진",
                },
            ],
        },
    }
```

---

## 8. Dependency Map

```
pyproject.toml dependencies:

[필수]
  aiohttp >= 3.9         # HTTP 클라이언트
  winotify >= 1.1        # Windows 알림 (win32만)

[선택]
  psutil >= 5.9          # 메모리 메트릭

[개발]
  pytest >= 8.0
  pytest-asyncio >= 0.23
  pytest-cov >= 4.1
  ruff >= 0.4
  mypy >= 1.9
  aioresponses >= 0.7    # aiohttp mock

[확장 - telegram]
  (aiohttp 재사용)
```

---

## 9. Phase 2+ Extension Roadmap

```
Phase 2 Extensions (고도화):
├── [EXT-01] 다중 노선 동시 모니터링
│   ├── Orchestrator에 다중 MonitorAgent 관리
│   └── asyncio.TaskGroup 활용
│
├── [EXT-02] Telegram Bot 연동
│   ├── src/skills/telegram.py
│   ├── Bot 명령어: /watch, /stop, /status
│   └── Inline 알림 메시지
│
├── [EXT-03] 웹 대시보드
│   ├── FastAPI + HTMX (경량)
│   ├── 실시간 모니터링 상태 표시
│   └── SSE (Server-Sent Events) 업데이트
│
├── [EXT-04] 히스토리 시각화
│   ├── SQLite 기반 조회 기록 저장
│   └── 시간대별 좌석 가용성 차트
│
└── [EXT-05] Docker 컨테이너화
    ├── Alpine 기반 경량 이미지
    ├── 환경변수 기반 설정
    └── docker-compose (웹 대시보드 + 에이전트)

Phase 3 Extensions (확장):
├── [EXT-06] SRT 지원 추가
├── [EXT-07] 환승 경로 조합 감지
├── [EXT-08] 가격 변동 알림
└── [EXT-09] 모바일 앱 (Flutter)
```

---

## 10. Git Branch Strategy

```
main
  └── develop
       ├── feature/P1-project-setup
       ├── feature/P2-input-agent
       ├── feature/P2-monitor-agent
       ├── feature/P2-notifier-agent
       ├── feature/P2-health-agent
       ├── feature/P2-orchestrator
       ├── feature/P3-integration-tests
       ├── feature/P3-error-handling
       ├── feature/P4-docker
       └── feature/P4-ci-cd

커밋 메시지 컨벤션:
  feat:     새 기능
  fix:      버그 수정
  refactor: 리팩토링
  test:     테스트 추가/수정
  docs:     문서
  chore:    설정/빌드

예시:
  feat(monitor): 적응형 폴링 스케줄러 구현
  fix(notifier): Windows Toast 알림 인코딩 오류 수정
  test(seat-checker): 자정 교차 시간 계산 테스트 추가
  refactor(skills): BaseSkill 인터페이스 적용
```

---

## 11. Quality Gates

각 Phase 완료 전 통과해야 하는 품질 기준:

| 게이트 | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|--------|---------|---------|---------|---------|
| ruff check (0 errors) | O | O | O | O |
| mypy (0 errors) | O | O | O | O |
| pytest (100% pass) | O | O | O | O |
| 커버리지 | - | > 70% | > 80% | > 85% |
| 메모리 < 50MB | - | - | O | O |
| 6시간 세션 안정성 | - | - | O | O |
| Docker 빌드 | - | - | - | O |
| CI 파이프라인 그린 | - | - | - | O |

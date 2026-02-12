# Korail Seat Notifier - Claude Code Project Config

## Project Overview
코레일(Korail) 좌석 빈자리 감지 및 알림 시스템. Multi-Agent 아키텍처 기반.

## Architecture
- **Pattern**: Prompt → Agent → Skill Pipeline (Multi-Agent)
- **Agents**: Orchestrator, Input, Monitor, Notifier, Health
- **Language**: Python 3.11+, asyncio 기반
- **Key Docs**: AGENTS.md (에이전트 설계), SKILLS.md (스킬 명세), PIPELINE.md (개발 파이프라인)

## Code Conventions
- **Immutable data**: dataclass(frozen=True, slots=True) 사용
- **Memory**: `__slots__` 필수, tuple > list (불변 컬렉션)
- **Async**: 모든 I/O는 async/await, aiohttp 사용
- **Naming**: snake_case, 한국어 주석 허용
- **Type hints**: 모든 public 함수에 타입 힌트 필수
- **Error handling**: 에이전트별 격리, Circuit Breaker 패턴

## Project Structure
```
src/models/     - 데이터 모델 (TrainQuery, AgentConfig, Events)
src/agents/     - 에이전트 (Orchestrator, Input, Monitor, Notifier, Health)
src/skills/     - 스킬 (Parser, Validation, SeatChecker, Notifier, Poller)
src/agent/      - 레거시 (기존 KorailAgent, state, metrics)
src/utils/      - 유틸 (RateLimiter, Logging)
tests/unit/     - 단위 테스트
tests/integration/ - 통합 테스트
```

## Commands
- Test: `pytest tests/ -v`
- Lint: `ruff check src/ tests/`
- Type check: `mypy src/`
- Run: `python -m src.main -d 서울 -a 부산 --date 2026-02-14 --time-start 08:00 --time-end 12:00`

## Constraints
- 알림 전용 (자동 예매 금지)
- 조회 간격 최소 30초
- 세션 최대 6시간 / 720요청
- 메모리 50MB 이하
- robots.txt 준수

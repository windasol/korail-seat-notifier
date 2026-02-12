"""코레일 좌석 알림 시스템 - CLI 진입점

사용 예시:
    python -m src.main --departure 서울 --arrival 부산 \
        --date 2026-02-14 --time-start 08:00 --time-end 12:00

    python -m src.main (대화형 모드)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from datetime import date, time

from src.agents.orchestrator import OrchestratorAgent
from src.models.config import AgentConfig
from src.models.query import TrainQuery
from src.skills.station_data import STATION_CODES, validate_station
from src.utils.logging_config import setup_logging


BANNER = r"""
  ╔══════════════════════════════════════════════╗
  ║   코레일 좌석 빈자리 알림 시스템 v2.0.0      ║
  ║   Korail Seat Availability Notifier          ║
  ║   Multi-Agent Architecture                   ║
  ╚══════════════════════════════════════════════╝
"""


def parse_date(s: str) -> date:
    """YYYY-MM-DD 또는 YYYYMMDD 형식의 날짜 파싱"""
    s = s.strip().replace("-", "")
    if len(s) != 8:
        raise argparse.ArgumentTypeError(
            f"날짜 형식이 올바르지 않습니다: '{s}' (YYYY-MM-DD)"
        )
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def parse_time(s: str) -> time:
    """HH:MM 또는 HHMM 형식의 시간 파싱"""
    s = s.strip().replace(":", "")
    if len(s) < 4:
        s = s.ljust(4, "0")
    return time(int(s[:2]), int(s[2:4]))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="코레일 좌석 빈자리 알림 (Multi-Agent v2.0)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "예시:\n"
            "  python -m src.main -d 서울 -a 부산 "
            "--date 2026-02-14 --time-start 08:00 --time-end 12:00\n"
            "  python -m src.main  (대화형 모드)"
        ),
    )
    p.add_argument("-d", "--departure", help="출발역")
    p.add_argument("-a", "--arrival", help="도착역")
    p.add_argument("--date", type=parse_date, help="출발 날짜 (YYYY-MM-DD)")
    p.add_argument("--time-start", type=parse_time, help="희망 시작 시간 (HH:MM)")
    p.add_argument("--time-end", type=parse_time, help="희망 종료 시간 (HH:MM)")
    p.add_argument(
        "--train-type",
        default="KTX",
        choices=["KTX", "KTX-산천", "KTX-이음", "ITX-새마을", "ITX-청춘", "무궁화", "전체"],
        help="열차 종류 (기본: KTX)",
    )
    p.add_argument(
        "--seat-type",
        default="일반실",
        choices=["일반실", "특실"],
        help="좌석 유형 (기본: 일반실)",
    )
    p.add_argument(
        "--passengers",
        type=int,
        default=1,
        help="승객 수 (1-9, 기본: 1)",
    )
    p.add_argument(
        "--notify",
        default="desktop,sound",
        help="알림 방법 (desktop,sound,webhook 콤마 구분)",
    )
    p.add_argument(
        "--interval",
        type=float,
        default=30.0,
        help="조회 간격 초 (기본: 30, 최소: 30)",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    p.add_argument("--log-file", default=None, help="로그 파일 경로")
    return p


def interactive_input() -> TrainQuery:
    """대화형 입력으로 TrainQuery 생성"""
    print(BANNER)
    print("  대화형 모드 - 아래 정보를 입력하세요\n")

    stations = sorted(STATION_CODES.keys())
    print(f"  지원 역: {', '.join(stations)}\n")

    while True:
        try:
            dep = input("  출발역: ").strip()
            dep = validate_station(dep)
            break
        except ValueError as e:
            print(f"  [오류] {e}\n")

    while True:
        try:
            arr = input("  도착역: ").strip()
            arr = validate_station(arr)
            if arr == dep:
                print("  [오류] 출발역과 도착역이 같습니다\n")
                continue
            break
        except ValueError as e:
            print(f"  [오류] {e}\n")

    while True:
        try:
            d = input("  출발 날짜 (YYYY-MM-DD): ").strip()
            dep_date = parse_date(d)
            if dep_date < date.today():
                print("  [오류] 과거 날짜는 선택할 수 없습니다\n")
                continue
            break
        except (ValueError, argparse.ArgumentTypeError) as e:
            print(f"  [오류] {e}\n")

    while True:
        try:
            ts = input("  희망 시작 시간 (HH:MM): ").strip()
            time_start = parse_time(ts)
            te = input("  희망 종료 시간 (HH:MM): ").strip()
            time_end = parse_time(te)
            if time_end <= time_start:
                print("  [오류] 종료 시간이 시작 시간보다 커야 합니다\n")
                continue
            break
        except (ValueError, argparse.ArgumentTypeError) as e:
            print(f"  [오류] {e}\n")

    train_type = input("  열차 종류 (KTX/무궁화/전체, 기본 KTX): ").strip()
    if not train_type:
        train_type = "KTX"

    seat = input("  좌석 유형 (일반실/특실, 기본 일반실): ").strip()
    if not seat:
        seat = "일반실"

    pax = input("  승객 수 (기본 1): ").strip()
    pax_count = int(pax) if pax else 1

    return TrainQuery(
        departure_station=dep,
        arrival_station=arr,
        departure_date=dep_date,
        preferred_time_start=time_start,
        preferred_time_end=time_end,
        train_type=train_type,
        seat_type=seat,
        passenger_count=pax_count,
    )


def build_query_from_args(args: argparse.Namespace) -> TrainQuery:
    """CLI 인자로부터 TrainQuery 생성"""
    dep = validate_station(args.departure)
    arr = validate_station(args.arrival)
    return TrainQuery(
        departure_station=dep,
        arrival_station=arr,
        departure_date=args.date,
        preferred_time_start=args.time_start,
        preferred_time_end=args.time_end,
        train_type=args.train_type,
        seat_type=args.seat_type,
        passenger_count=args.passengers,
    )


async def run(query: TrainQuery, config: AgentConfig) -> None:
    """OrchestratorAgent 기반 실행"""
    orchestrator = OrchestratorAgent(config)

    loop = asyncio.get_running_loop()

    def _signal_handler() -> None:
        print("\n\n  Ctrl+C 감지 - 모니터링 중지 중...")
        orchestrator.stop()

    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGINT, _signal_handler)
        loop.add_signal_handler(signal.SIGTERM, _signal_handler)

    print(f"\n  모니터링 시작: {query.summary()}")
    print("  중지하려면 Ctrl+C를 누르세요\n")

    try:
        metrics = await orchestrator.run(query)
        print(f"\n{metrics.summary()}")
    except KeyboardInterrupt:
        orchestrator.stop()


def cli_entry() -> None:
    """CLI 진입점 (pyproject.toml scripts에서 호출)"""
    main()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(
        level=args.log_level,
        log_file=args.log_file,
    )

    if args.departure and args.arrival and args.date and args.time_start and args.time_end:
        query = build_query_from_args(args)
    else:
        query = interactive_input()

    # 최소 간격 30초 준수 (robots.txt)
    interval = max(args.interval, 30.0)
    notify_methods = [m.strip() for m in args.notify.split(",") if m.strip()]

    config = AgentConfig(
        base_interval=interval,
        notification_methods=notify_methods,
        webhook_url=os.environ.get("KORAIL_WEBHOOK_URL", ""),
    )

    print(BANNER)

    try:
        asyncio.run(run(query, config))
    except KeyboardInterrupt:
        print("\n  프로그램 종료")
        sys.exit(0)


if __name__ == "__main__":
    main()

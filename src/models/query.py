"""데이터 모델: 열차 조회 요청, 열차 정보, 조회 결과

모든 모델은 frozen=True + slots=True로 불변성과 메모리 효율을 보장한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import Literal


@dataclass(frozen=True, slots=True)
class TrainQuery:
    """불변 조회 요청 객체"""

    departure_station: str
    arrival_station: str
    departure_date: date
    preferred_time_start: time
    preferred_time_end: time
    train_type: Literal[
        "KTX", "KTX-산천", "KTX-이음",
        "ITX-새마을", "ITX-청춘", "무궁화", "전체",
    ] = "KTX"
    seat_type: Literal["일반실", "특실"] = "일반실"
    passenger_count: int = 1

    def __post_init__(self) -> None:
        if self.passenger_count < 1 or self.passenger_count > 9:
            raise ValueError("승객 수는 1~9명이어야 합니다")
        if self.preferred_time_end <= self.preferred_time_start:
            raise ValueError("종료 시간이 시작 시간보다 커야 합니다")

    def summary(self) -> str:
        return (
            f"{self.departure_station}→{self.arrival_station} "
            f"{self.departure_date} "
            f"{self.preferred_time_start:%H:%M}~{self.preferred_time_end:%H:%M} "
            f"{self.train_type} {self.seat_type} {self.passenger_count}명"
        )


@dataclass(frozen=True, slots=True)
class TrainInfo:
    """개별 열차 정보"""

    train_no: str
    train_type: str
    departure_time: time
    arrival_time: time
    general_seats: int
    special_seats: int
    duration_minutes: int

    @property
    def has_seats(self) -> bool:
        return self.general_seats > 0 or self.special_seats > 0

    def display(self) -> str:
        parts = [
            f"{self.train_type} {self.train_no}호 "
            f"{self.departure_time:%H:%M}→{self.arrival_time:%H:%M}"
        ]
        seats = []
        if self.general_seats > 0:
            seats.append(f"일반 {self.general_seats}석")
        if self.special_seats > 0:
            seats.append(f"특실 {self.special_seats}석")
        if seats:
            parts.append(f"({' / '.join(seats)})")
        return " ".join(parts)


@dataclass(frozen=True, slots=True)
class CheckResult:
    """좌석 조회 결과"""

    query_timestamp: float
    trains: tuple[TrainInfo, ...]
    seats_available: bool
    raw_response_size: int

    @property
    def available_trains(self) -> tuple[TrainInfo, ...]:
        return tuple(t for t in self.trains if t.has_seats)

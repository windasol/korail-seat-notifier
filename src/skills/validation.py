"""입력 검증 스킬

비즈니스 규칙에 따라 입력값을 검증하고 TrainQuery를 생성한다.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from typing import Any

from src.models.query import TrainQuery
from src.skills.station_data import validate_station


class ValidationSkill:
    """입력 검증 스킬"""

    MAX_FUTURE_DAYS = 90

    def validate_query(self, data: dict[str, Any]) -> TrainQuery:
        """전체 검증 후 불변 TrainQuery 반환. 실패 시 ValueError."""

        dep = data.get("departure")
        arr = data.get("arrival")
        dep_date = data.get("date")
        time_start = data.get("time_start")
        time_end = data.get("time_end")
        train_type = data.get("train_type", "KTX")
        seat_type = data.get("seat_type", "일반실")
        passengers = data.get("passengers", 1)

        # 필수 필드 체크
        if not dep:
            raise ValueError("출발역이 입력되지 않았습니다")
        if not arr:
            raise ValueError("도착역이 입력되지 않았습니다")
        if not dep_date:
            raise ValueError("출발 날짜가 입력되지 않았습니다")
        if not time_start:
            raise ValueError("시작 시간이 입력되지 않았습니다")
        if not time_end:
            raise ValueError("종료 시간이 입력되지 않았습니다")

        # R1, R2: 역 검증 + 정규화
        dep = validate_station(dep)
        arr = validate_station(arr)

        # R3: 동일 출도착
        if dep == arr:
            raise ValueError("출발역과 도착역이 같습니다")

        # R4: 과거 날짜
        self.validate_date(dep_date)

        # R6: 시간 범위
        self.validate_time_range(time_start, time_end)

        # R7: 승객 수
        self.validate_passengers(passengers)

        return TrainQuery(
            departure_station=dep,
            arrival_station=arr,
            departure_date=dep_date,
            preferred_time_start=time_start,
            preferred_time_end=time_end,
            train_type=train_type,
            seat_type=seat_type,
            passenger_count=passengers,
        )

    def validate_date(self, d: date) -> None:
        """과거 날짜, 90일 이후 검증"""
        today = date.today()
        if d < today:
            raise ValueError("과거 날짜는 선택할 수 없습니다")
        if d > today + timedelta(days=self.MAX_FUTURE_DAYS):
            raise ValueError(
                f"{self.MAX_FUTURE_DAYS}일 이내의 날짜만 선택할 수 있습니다"
            )

    @staticmethod
    def validate_time_range(start: time, end: time) -> None:
        """시작 < 종료 검증"""
        if end <= start:
            raise ValueError("종료 시간이 시작 시간보다 커야 합니다")

    @staticmethod
    def validate_passengers(count: int) -> None:
        """1~9명 범위 검증"""
        if count < 1 or count > 9:
            raise ValueError("승객 수는 1~9명이어야 합니다")

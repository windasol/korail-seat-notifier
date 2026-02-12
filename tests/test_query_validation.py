"""TrainQuery 유효성 검증 테스트"""

import pytest
from datetime import date, time

from src.models.query import TrainQuery, TrainInfo, CheckResult


class TestTrainQuery:
    def test_valid_query(self):
        q = TrainQuery(
            departure_station="서울",
            arrival_station="부산",
            departure_date=date(2026, 3, 1),
            preferred_time_start=time(8, 0),
            preferred_time_end=time(12, 0),
        )
        assert q.departure_station == "서울"
        assert q.train_type == "KTX"
        assert q.seat_type == "일반실"
        assert q.passenger_count == 1

    def test_passenger_count_too_low(self):
        with pytest.raises(ValueError, match="승객 수"):
            TrainQuery(
                departure_station="서울",
                arrival_station="부산",
                departure_date=date(2026, 3, 1),
                preferred_time_start=time(8, 0),
                preferred_time_end=time(12, 0),
                passenger_count=0,
            )

    def test_passenger_count_too_high(self):
        with pytest.raises(ValueError, match="승객 수"):
            TrainQuery(
                departure_station="서울",
                arrival_station="부산",
                departure_date=date(2026, 3, 1),
                preferred_time_start=time(8, 0),
                preferred_time_end=time(12, 0),
                passenger_count=10,
            )

    def test_invalid_time_range(self):
        with pytest.raises(ValueError, match="종료 시간"):
            TrainQuery(
                departure_station="서울",
                arrival_station="부산",
                departure_date=date(2026, 3, 1),
                preferred_time_start=time(12, 0),
                preferred_time_end=time(8, 0),
            )

    def test_frozen(self):
        q = TrainQuery(
            departure_station="서울",
            arrival_station="부산",
            departure_date=date(2026, 3, 1),
            preferred_time_start=time(8, 0),
            preferred_time_end=time(12, 0),
        )
        with pytest.raises(AttributeError):
            q.departure_station = "대전"

    def test_summary(self):
        q = TrainQuery(
            departure_station="서울",
            arrival_station="부산",
            departure_date=date(2026, 3, 1),
            preferred_time_start=time(8, 0),
            preferred_time_end=time(12, 0),
        )
        s = q.summary()
        assert "서울" in s
        assert "부산" in s
        assert "08:00" in s


class TestTrainInfo:
    def test_has_seats(self):
        t = TrainInfo(
            train_no="101",
            train_type="KTX",
            departure_time=time(8, 0),
            arrival_time=time(10, 30),
            general_seats=5,
            special_seats=0,
            duration_minutes=150,
        )
        assert t.has_seats is True

    def test_no_seats(self):
        t = TrainInfo(
            train_no="101",
            train_type="KTX",
            departure_time=time(8, 0),
            arrival_time=time(10, 30),
            general_seats=0,
            special_seats=0,
            duration_minutes=150,
        )
        assert t.has_seats is False

    def test_display(self):
        t = TrainInfo(
            train_no="101",
            train_type="KTX",
            departure_time=time(8, 0),
            arrival_time=time(10, 30),
            general_seats=3,
            special_seats=1,
            duration_minutes=150,
        )
        d = t.display()
        assert "101" in d
        assert "일반 3석" in d
        assert "특실 1석" in d


class TestCheckResult:
    def test_available_trains(self):
        trains = (
            TrainInfo("101", "KTX", time(8, 0), time(10, 0), 5, 0, 120),
            TrainInfo("103", "KTX", time(9, 0), time(11, 0), 0, 0, 120),
            TrainInfo("105", "KTX", time(10, 0), time(12, 0), 0, 2, 120),
        )
        r = CheckResult(
            query_timestamp=0.0,
            trains=trains,
            seats_available=True,
            raw_response_size=1024,
        )
        available = r.available_trains
        assert len(available) == 2
        assert available[0].train_no == "101"
        assert available[1].train_no == "105"

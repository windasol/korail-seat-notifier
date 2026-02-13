"""좌석 조회 스킬 테스트"""

import pytest
from datetime import date, time

from src.skills.seat_checker import (
    SeatCheckerSkill,
    _parse_time,
    _seat_count_from_code,
    _calc_duration,
)
from src.skills.station_data import validate_station, get_station_code
from src.models.query import TrainQuery


class TestParseTime:
    def test_normal(self):
        assert _parse_time("083000") == time(8, 30)

    def test_midnight(self):
        assert _parse_time("000000") == time(0, 0)

    def test_evening(self):
        assert _parse_time("233000") == time(23, 30)

    def test_short_string(self):
        assert _parse_time("0830") == time(8, 30)


class TestSeatCountFromCode:
    def test_sold_out_code(self):
        assert _seat_count_from_code("00", "매진") == 0

    def test_sold_out_code_empty_name(self):
        assert _seat_count_from_code("00", "") == 0

    def test_available_many(self):
        assert _seat_count_from_code("11", "좌석많음") == 99

    def test_available_여유(self):
        assert _seat_count_from_code("11", "여유있음") == 99

    def test_available_possible(self):
        assert _seat_count_from_code("11", "가능") == 99

    def test_available_digits(self):
        assert _seat_count_from_code("11", "5석") == 5

    def test_available_no_info(self):
        # "예약하기" 같이 숫자 없는 텍스트 → 1석으로 가정 (available 코드 신뢰)
        assert _seat_count_from_code("11", "예약하기") == 1

    def test_available_no_info_empty(self):
        assert _seat_count_from_code("11", "") == 1

    def test_code_13_available(self):
        assert _seat_count_from_code("13", "좌석많음") == 99

    def test_empty_code(self):
        assert _seat_count_from_code("", "") == 0

    # ── 핵심 버그 케이스: code="11"인데 name에 매진 텍스트 ─────────
    def test_code_11_but_name_매진(self):
        """code=11이어도 name이 '매진'이면 0을 반환해야 함 (이전에는 1 반환하는 버그)"""
        assert _seat_count_from_code("11", "매진") == 0

    def test_code_11_but_name_대기(self):
        assert _seat_count_from_code("11", "대기접수") == 0

    def test_code_13_but_name_마감(self):
        assert _seat_count_from_code("13", "마감") == 0

    def test_code_11_but_name_없음(self):
        assert _seat_count_from_code("11", "좌석없음") == 0


class TestCalcDuration:
    def test_normal(self):
        assert _calc_duration(time(8, 0), time(10, 30)) == 150

    def test_same(self):
        assert _calc_duration(time(8, 0), time(8, 0)) == 1440  # 자정 넘김

    def test_cross_midnight(self):
        # 23:00 출발 → 01:00 도착 = 2시간 = 120분
        assert _calc_duration(time(23, 0), time(1, 0)) == 120


class TestStationValidation:
    def test_valid(self):
        assert validate_station("서울") == "서울"

    def test_alias(self):
        assert validate_station("서울역") == "서울"

    def test_alias_ulsan(self):
        assert validate_station("울산") == "울산(통도사)"

    def test_whitespace(self):
        assert validate_station("  서울  ") == "서울"

    def test_invalid(self):
        with pytest.raises(ValueError, match="지원하지 않는 역"):
            validate_station("없는역")

    def test_get_code(self):
        code = get_station_code("서울")
        assert code == "0001"

    def test_busan_code_fixed(self):
        assert get_station_code("부산") == "0032"

    def test_dongdaegu_code_fixed(self):
        assert get_station_code("동대구") == "0508"


class TestBuildParams:
    def test_params_structure(self):
        q = TrainQuery(
            departure_station="서울",
            arrival_station="부산",
            departure_date=date(2026, 3, 1),
            preferred_time_start=time(8, 0),
            preferred_time_end=time(12, 0),
        )
        params = SeatCheckerSkill._build_params(q)
        assert params["txtGoStart"] == "서울"
        assert params["txtGoEnd"] == "부산"
        assert params["txtGoAbrdDt"] == "20260301"
        assert params["txtGoHour"] == "080000"
        assert params["selGoTrain"] == "100"  # KTX
        assert params["Device"] == "AD"
        assert params["Version"] == "190617001"
        assert params["radJobId"] == "1"

    def test_train_type_all_uses_code_00(self):
        """전체 선택 시 코드 '00' 사용 (109는 ITX-청춘 코드)"""
        q = TrainQuery(
            departure_station="서울",
            arrival_station="부산",
            departure_date=date(2026, 3, 1),
            preferred_time_start=time(8, 0),
            preferred_time_end=time(12, 0),
            train_type="전체",
        )
        params = SeatCheckerSkill._build_params(q)
        assert params["selGoTrain"] == "00"
        assert params["txtTrnGpCd"] == "00"

    def test_train_type_itx_cheongchun(self):
        """ITX-청춘 코드는 109"""
        q = TrainQuery(
            departure_station="서울",
            arrival_station="부산",
            departure_date=date(2026, 3, 1),
            preferred_time_start=time(8, 0),
            preferred_time_end=time(12, 0),
            train_type="ITX-청춘",
        )
        params = SeatCheckerSkill._build_params(q)
        assert params["selGoTrain"] == "109"


class TestParseResponse:
    def test_empty_response(self):
        q = TrainQuery(
            departure_station="서울",
            arrival_station="부산",
            departure_date=date(2026, 3, 1),
            preferred_time_start=time(8, 0),
            preferred_time_end=time(12, 0),
        )
        result = SeatCheckerSkill._parse_response({}, q)
        assert result == []

    def test_parse_trains(self):
        q = TrainQuery(
            departure_station="서울",
            arrival_station="부산",
            departure_date=date(2026, 3, 1),
            preferred_time_start=time(8, 0),
            preferred_time_end=time(12, 0),
        )
        data = {
            "trn_infos": {
                "trn_info": [
                    {
                        "h_trn_no": "101",
                        "h_trn_clsf_nm": "KTX",
                        "h_dpt_tm": "090000",
                        "h_arv_tm": "113000",
                        "h_gen_rsv_cd": "11",
                        "h_gen_rsv_nm": "좌석많음",
                        "h_spe_rsv_cd": "00",
                        "h_spe_rsv_nm": "매진",
                    },
                    {
                        "h_trn_no": "103",
                        "h_trn_clsf_nm": "KTX",
                        "h_dpt_tm": "140000",  # 시간 범위 밖
                        "h_arv_tm": "163000",
                        "h_gen_rsv_cd": "11",
                        "h_gen_rsv_nm": "좌석많음",
                        "h_spe_rsv_cd": "11",
                        "h_spe_rsv_nm": "좌석많음",
                    },
                ],
            },
        }
        trains = SeatCheckerSkill._parse_response(data, q)
        assert len(trains) == 1
        assert trains[0].train_no == "101"
        assert trains[0].general_seats == 99
        assert trains[0].special_seats == 0

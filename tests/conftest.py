"""pytest 공통 픽스처

모든 테스트에서 공유하는 샘플 데이터와 Mock 객체를 제공한다.
"""

from __future__ import annotations

from datetime import date, time

import pytest

from src.models.config import AgentConfig
from src.models.query import CheckResult, TrainInfo, TrainQuery


@pytest.fixture
def sample_query() -> TrainQuery:
    """표준 테스트용 TrainQuery (서울 → 부산, KTX)"""
    return TrainQuery(
        departure_station="서울",
        arrival_station="부산",
        departure_date=date(2026, 3, 1),
        preferred_time_start=time(8, 0),
        preferred_time_end=time(12, 0),
    )


@pytest.fixture
def sample_config() -> AgentConfig:
    """테스트용 빠른 설정 (간격 1초, 세션 10초)"""
    return AgentConfig(
        base_interval=1.0,
        max_interval=5.0,
        max_session_duration=10.0,
        max_requests_per_session=5,
        notification_cooldown=0.1,  # 테스트용 짧은 쿨다운
        notification_methods=["desktop"],
    )


@pytest.fixture
def sample_train_info() -> TrainInfo:
    """좌석 있는 열차 정보"""
    return TrainInfo(
        train_no="101",
        train_type="KTX",
        departure_time=time(9, 0),
        arrival_time=time(11, 30),
        general_seats=5,
        special_seats=0,
        duration_minutes=150,
    )


@pytest.fixture
def sample_train_info_no_seat() -> TrainInfo:
    """매진 열차 정보"""
    return TrainInfo(
        train_no="103",
        train_type="KTX",
        departure_time=time(10, 0),
        arrival_time=time(12, 30),
        general_seats=0,
        special_seats=0,
        duration_minutes=150,
    )


@pytest.fixture
def check_result_with_seats(sample_train_info: TrainInfo) -> CheckResult:
    """빈자리 있는 조회 결과"""
    from time import monotonic
    return CheckResult(
        query_timestamp=monotonic(),
        trains=(sample_train_info,),
        seats_available=True,
        raw_response_size=1024,
    )


@pytest.fixture
def check_result_no_seats(sample_train_info_no_seat: TrainInfo) -> CheckResult:
    """빈자리 없는 조회 결과"""
    from time import monotonic
    return CheckResult(
        query_timestamp=monotonic(),
        trains=(sample_train_info_no_seat,),
        seats_available=False,
        raw_response_size=512,
    )


@pytest.fixture
def mock_api_response() -> dict:  # type: ignore[type-arg]
    """코레일 API 정상 응답 mock (좌석 가능)"""
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
def mock_api_response_no_seats() -> dict:  # type: ignore[type-arg]
    """코레일 API 응답 mock (전체 매진)"""
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

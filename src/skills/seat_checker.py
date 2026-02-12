"""좌석 조회 스킬

코레일 모바일 API를 통해 좌석 가용성을 확인한다.
로그인 불필요 (비회원 조회).
API: smart.letskorail.com (Korail 공식 모바일 앱 백엔드)
"""

from __future__ import annotations

import logging
from datetime import time
from time import monotonic
from typing import ClassVar, Optional

import aiohttp

from src.models.query import CheckResult, TrainInfo, TrainQuery

logger = logging.getLogger("korail.skill.seat_checker")

# 열차 종류 → 코레일 코드
TRAIN_TYPE_CODES: dict[str, str] = {
    "KTX": "100",
    "KTX-산천": "100",
    "KTX-이음": "100",
    "ITX-새마을": "101",
    "ITX-청춘": "109",
    "무궁화": "102",
    "전체": "109",
}

# 좌석 속성 코드
SEAT_ATTR_CODES: dict[str, str] = {
    "일반실": "015",
    "특실": "011",
}

# 좌석 예약 코드 → 가용 여부
# h_gen_rsv_cd / h_spe_rsv_cd 값 의미:
#   "11" or "13" = 좌석있음
#   "00"         = 매진
_RSV_CODE_AVAILABLE = {"11", "13"}


class SeatCheckerSkill:
    """코레일 모바일 API 좌석 조회 스킬"""

    _session: ClassVar[Optional[aiohttp.ClientSession]] = None

    # 코레일 공식 모바일 앱이 사용하는 API 서버
    BASE_URL: ClassVar[str] = (
        "https://smart.letskorail.com:443"
        "/classes/com.korail.mobile.seatMovie.ScheduleView"
    )

    # 모바일 앱 User-Agent (korail2 라이브러리 참조)
    HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Dalvik/2.1.0 (Linux; U; Android 5.1.1; Nexus 4 Build/LMY48T)"
        ),
        "Accept": "application/json",
    }

    def __init__(
        self,
        request_timeout: float = 15.0,
        connect_timeout: float = 5.0,
        max_connections: int = 3,
    ) -> None:
        self._request_timeout = request_timeout
        self._connect_timeout = connect_timeout
        self._max_connections = max_connections

    @classmethod
    async def _get_session(
        cls,
        request_timeout: float = 15.0,
        connect_timeout: float = 5.0,
        max_connections: int = 3,
    ) -> aiohttp.ClientSession:
        if cls._session is None or cls._session.closed:
            timeout = aiohttp.ClientTimeout(
                total=request_timeout,
                connect=connect_timeout,
            )
            connector = aiohttp.TCPConnector(
                limit=max_connections,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )
            cls._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers=cls.HEADERS,
            )
        return cls._session

    @classmethod
    async def close(cls) -> None:
        if cls._session and not cls._session.closed:
            await cls._session.close()
            cls._session = None

    async def check(self, query: TrainQuery) -> CheckResult:
        """좌석 가용성 조회 실행"""
        session = await self._get_session(
            self._request_timeout,
            self._connect_timeout,
            self._max_connections,
        )
        params = self._build_params(query)
        ts = monotonic()

        async with session.get(self.BASE_URL, params=params) as resp:
            resp.raise_for_status()
            # 모바일 API는 JSON이지만 Content-Type을 text/html로 반환하므로
            # content_type 검사 없이 파싱
            data = await resp.json(content_type=None)
            raw_size = resp.content_length or len(await resp.read()) if False else 0

        # API 오류 응답 처리
        result_code = data.get("strResult", "")
        if result_code == "FAIL":
            msg_cd = data.get("h_msg_cd", "")
            msg_txt = data.get("h_msg_txt", "")
            raise RuntimeError(f"API 오류 [{msg_cd}]: {msg_txt}")

        trains = self._parse_response(data, query)
        available = any(t.has_seats for t in trains)

        return CheckResult(
            query_timestamp=ts,
            trains=tuple(trains),
            seats_available=available,
            raw_response_size=raw_size,
        )

    @staticmethod
    def _build_params(query: TrainQuery) -> dict[str, str]:
        """모바일 API 요청 파라미터 구성"""
        train_code = TRAIN_TYPE_CODES.get(query.train_type, "109")
        seat_code = SEAT_ATTR_CODES.get(query.seat_type, "015")
        return {
            # 모바일 앱 인증 파라미터
            "Device":         "AD",
            "Version":        "190617001",
            # 조회 파라미터
            "txtGoStart":     query.departure_station,
            "txtGoEnd":       query.arrival_station,
            "txtGoAbrdDt":    query.departure_date.strftime("%Y%m%d"),
            "txtGoHour":      query.preferred_time_start.strftime("%H%M%S"),
            "selGoTrain":     train_code,
            "txtTrnGpCd":     train_code,
            "txtSeatAttCd":   seat_code,
            # 인원 파라미터
            "txtPsgFlg_1":    str(query.passenger_count),
            "txtPsgFlg_2":    "0",
            "txtPsgFlg_3":    "0",
            "txtPsgFlg_4":    "0",
            "txtPsgFlg_5":    "0",
            "txtCardPsgCnt":  "0",
            "txtTotPsgCnt":   str(query.passenger_count),
            # 기타 필수 파라미터
            "txtSeatAttCd_2": "000",
            "txtSeatAttCd_3": "000",
            "txtSeatAttCd_4": "015",
            "radJobId":       "1",
            "txtMenuId":      "11",
            "txtGdNo":        "",
            "txtJobDv":       "",
        }

    @staticmethod
    def _parse_response(
        data: dict,  # type: ignore[type-arg]
        query: TrainQuery,
    ) -> list[TrainInfo]:
        """응답 파싱 - 시간 범위 필터 적용"""
        trains: list[TrainInfo] = []
        trn_infos = data.get("trn_infos", {})
        if not trn_infos:
            return trains

        for item in trn_infos.get("trn_info", []):
            dep_time = _parse_time(item.get("h_dpt_tm", "000000"))
            arr_time = _parse_time(item.get("h_arv_tm", "000000"))

            # 시간 범위 필터
            if not (query.preferred_time_start
                    <= dep_time
                    <= query.preferred_time_end):
                continue

            # 좌석 가용성: rsv_cd 코드 우선, 없으면 nm 텍스트로 판단
            gen_cd = item.get("h_gen_rsv_cd", "00")
            spe_cd = item.get("h_spe_rsv_cd", "00")
            gen_nm = item.get("h_gen_rsv_nm", "")
            spe_nm = item.get("h_spe_rsv_nm", "")

            general_seats = _seat_count_from_code(gen_cd, gen_nm)
            special_seats = _seat_count_from_code(spe_cd, spe_nm)

            trains.append(TrainInfo(
                train_no=item.get("h_trn_no", ""),
                train_type=item.get("h_trn_clsf_nm", ""),
                departure_time=dep_time,
                arrival_time=arr_time,
                general_seats=general_seats,
                special_seats=special_seats,
                duration_minutes=_calc_duration(dep_time, arr_time),
            ))
        return trains


def _seat_count_from_code(code: str, name: str) -> int:
    """예약코드 + 텍스트로 잔여석 수 추정"""
    if code in _RSV_CODE_AVAILABLE:
        # 텍스트에서 구체적인 수 추출 시도
        if "많음" in name or "충분" in name or "가능" in name:
            return 99
        digits = "".join(c for c in name if c.isdigit())
        return int(digits) if digits else 1
    # 매진/대기/없음
    return 0


def _parse_time(s: str) -> time:
    """HHMMSS 또는 HHMM 문자열 → time 객체"""
    s = s.strip()
    if len(s) < 4:
        s = s.ljust(6, "0")
    return time(int(s[:2]), int(s[2:4]))


def _calc_duration(dep: time, arr: time) -> int:
    """출발/도착 시간으로 소요시간(분) 계산. 자정 교차 처리."""
    dep_min = dep.hour * 60 + dep.minute
    arr_min = arr.hour * 60 + arr.minute
    diff = arr_min - dep_min
    if diff <= 0:
        diff += 1440  # 자정 교차
    return diff

"""역 코드 매핑 및 검증

코레일 주요 역 코드와 별칭을 관리한다.
"""

from __future__ import annotations

# 역 이름 → 코레일 역 코드
STATION_CODES: dict[str, str] = {
    "서울": "0001",
    "용산": "0015",
    "영등포": "0020",
    "광명": "0502",
    "수원": "0055",
    "천안아산": "0297",
    "오송": "0298",
    "대전": "0010",
    "김천구미": "0507",
    "동대구": "0508",
    "경주": "0519",
    "포항": "0515",
    "울산(통도사)": "0930",
    "부산": "0032",
    "광주송정": "0036",
    "목포": "0041",
    "전주": "0045",
    "익산": "0030",
    "여수엑스포": "0049",
    "강릉": "0115",
    "평창": "0112",
    "진주": "0056",
}

# 별칭 → 정식 명칭
STATION_ALIASES: dict[str, str] = {
    "서울역": "서울",
    "용산역": "용산",
    "부산역": "부산",
    "대전역": "대전",
    "동대구역": "동대구",
    "울산": "울산(통도사)",
    "울산역": "울산(통도사)",
    "통도사": "울산(통도사)",
    "광주": "광주송정",
    "여수": "여수엑스포",
    "김천": "김천구미",
    "구미": "김천구미",
    "천안": "천안아산",
    "아산": "천안아산",
}


def validate_station(name: str) -> str:
    """역 이름 정규화 및 검증.

    별칭(서울역 → 서울)을 처리하고, 지원하지 않는 역이면 ValueError.
    """
    normalized = name.strip().replace(" ", "")

    # 별칭 변환
    if normalized in STATION_ALIASES:
        normalized = STATION_ALIASES[normalized]

    if normalized not in STATION_CODES:
        stations = ", ".join(sorted(STATION_CODES.keys()))
        raise ValueError(
            f"'{name}'은(는) 지원하지 않는 역입니다. "
            f"지원 역: {stations}"
        )
    return normalized


def get_station_code(name: str) -> str:
    """정규화된 역 이름 → 코레일 역 코드"""
    normalized = validate_station(name)
    return STATION_CODES[normalized]

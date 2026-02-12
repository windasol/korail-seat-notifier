# -*- coding: utf-8 -*-
from __future__ import annotations  # noqa: I001
"""
코레일 API 진단 스크립트 v2
실행: py -X utf8 debug_api.py
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import asyncio
import json

import aiohttp


SEP = "=" * 60

# 후보 엔드포인트들 (신/구 URL)
CANDIDATES = [
    {
        "desc": "[구] letskorail GET",
        "method": "GET",
        "url": "https://www.letskorail.com/ebizprd/EbizPrdSttnKeyListBy498.do",
    },
    {
        "desc": "[신] korail.com GET",
        "method": "GET",
        "url": "https://www.korail.com/ebizprd/EbizPrdSttnKeyListBy498.do",
    },
    {
        "desc": "[신] korail.com 열차조회 REST",
        "method": "GET",
        "url": "https://www.korail.com/stncab/stncJnyList.do",
    },
    {
        "desc": "[신] korail.com 홈",
        "method": "GET",
        "url": "https://www.korail.com/",
    },
]

COMMON_PARAMS = {
    "txtGoStart": "서울",
    "txtGoEnd": "부산",
    "txtGoAbrdDt": "20260310",
    "txtGoHour": "080000",
    "selGoTrain": "100",
    "txtSeatAttCd": "015",
    "txtPsgFlg_1": "1",
    "txtTotPsgCnt": "1",
    "txtSeatAttCd_2": "000",
    "txtSeatAttCd_3": "000",
    "txtSeatAttCd_4": "015",
    "radioJobId": "1",
    "txtMenuId": "11",
}

HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}


async def probe(session: aiohttp.ClientSession, candidate: dict) -> None:
    print(f"\n{SEP}")
    print(f"테스트: {candidate['desc']}")
    print(f"URL   : {candidate['url']}")

    try:
        async with session.get(
            candidate["url"],
            params=COMMON_PARAMS,
            allow_redirects=True,
        ) as resp:
            print(f"상태   : {resp.status}")
            print(f"최종URL: {resp.url}")
            print(f"Content-Type: {resp.content_type}")

            text = await resp.text(encoding="utf-8", errors="replace")
            print(f"응답길이: {len(text)}자")
            print(f"--- 응답 앞 600자 ---")
            print(text[:600])
            print("--- 끝 ---")

            # JSON 여부 확인
            if resp.content_type and "json" in resp.content_type:
                try:
                    data = json.loads(text)
                    print(f"JSON 파싱 성공! 최상위 키: {list(data.keys())}")
                    if "trn_infos" in data:
                        ti = data["trn_infos"]
                        trains = ti.get("trn_info", [])
                        if isinstance(trains, dict):
                            trains = [trains]
                        print(f"열차 수: {len(trains)}")
                        for i, t in enumerate(trains[:3]):
                            print(f"  [{i+1}] {t.get('h_trn_clsf_nm','')} "
                                  f"{t.get('h_trn_no','')}호 "
                                  f"{t.get('h_dpt_tm','')} -> {t.get('h_arv_tm','')} "
                                  f"일반:{t.get('h_rsv_psb_nm','')} "
                                  f"특실:{t.get('h_spe_rsv_psb_nm','')}")
                except Exception as e:
                    print(f"JSON 파싱 실패: {e}")

    except aiohttp.ClientConnectorError as e:
        print(f"연결 실패: {e}")
    except asyncio.TimeoutError:
        print("타임아웃 (15초)")
    except Exception as e:
        print(f"예외: {type(e).__name__}: {e}")


async def main() -> None:
    print(SEP)
    print("코레일 API 엔드포인트 진단")
    print(SEP)

    timeout = aiohttp.ClientTimeout(total=15, connect=8)
    async with aiohttp.ClientSession(
        headers=HEADERS_BROWSER, timeout=timeout
    ) as session:
        for c in CANDIDATES:
            await probe(session, c)

    print(f"\n{SEP}")
    print("진단 완료")
    print(SEP)


if __name__ == "__main__":
    asyncio.run(main())

# coding: utf-8
"""
코레일 모바일 API 테스트
korail2 라이브러리가 사용하는 smart.letskorail.com 엔드포인트 검증
실행: py -X utf8 debug_mobile_api.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import asyncio, json
import aiohttp

SEP = "-" * 60

# 코레일 모바일 앱이 사용하는 API (korail2 라이브러리 참조)
MOBILE_BASE = "https://smart.letskorail.com:443"
SEARCH_URL  = f"{MOBILE_BASE}/classes/com.korail.mobile.seatMovie.ScheduleView"

MOBILE_HEADERS = {
    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 5.1.1; Nexus 4 Build/LMY48T)",
    "Accept": "application/json",
    "Content-Type": "application/x-www-form-urlencoded",
}

SEARCH_PARAMS = {
    "Device":         "AD",
    "Version":        "190617001",
    "txtGoStart":     "서울",
    "txtGoEnd":       "부산",
    "txtGoAbrdDt":    "20260310",
    "txtGoHour":      "080000",
    "selGoTrain":     "100",       # KTX
    "txtPsgFlg_1":    "1",        # 어른 1명
    "txtPsgFlg_2":    "0",
    "txtPsgFlg_3":    "0",
    "txtPsgFlg_4":    "0",
    "txtPsgFlg_5":    "0",
    "txtCardPsgCnt":  "0",
    "txtTotPsgCnt":   "1",
    "txtSeatAttCd":   "015",
    "txtSeatAttCd_2": "000",
    "txtSeatAttCd_3": "000",
    "txtSeatAttCd_4": "015",
    "radJobId":       "1",
    "txtMenuId":      "11",
    "txtGdNo":        "",
    "txtJobDv":       "",
    "txtTrnGpCd":     "100",
}

async def main():
    print("=" * 60)
    print("코레일 모바일 API 테스트")
    print("=" * 60)

    timeout = aiohttp.ClientTimeout(total=15, connect=8)
    async with aiohttp.ClientSession(headers=MOBILE_HEADERS, timeout=timeout) as sess:

        print(f"\n[1] GET 방식 테스트")
        print(f"  URL: {SEARCH_URL}")
        try:
            async with sess.get(SEARCH_URL, params=SEARCH_PARAMS) as r:
                ct = r.content_type or ""
                text = await r.text(errors="replace")
                print(f"  상태: {r.status}, Content-Type: {ct}")
                print(f"  길이: {len(text)}자")
                print(f"  앞 600자:\n{text[:600]}")
                if "json" in ct or text.strip()[:1] in "{[":
                    try:
                        d = json.loads(text)
                        print(f"  JSON 최상위 키: {list(d.keys()) if isinstance(d, dict) else type(d)}")
                        # 열차 목록 확인
                        trn_infos = d.get("trn_infos", {})
                        if trn_infos:
                            trains = trn_infos.get("trn_info", [])
                            print(f"  열차 수: {len(trains)}개")
                            if trains:
                                print(f"  첫 열차: {trains[0]}")
                    except json.JSONDecodeError as e:
                        print(f"  JSON 파싱 실패: {e}")
        except Exception as e:
            print(f"  오류: {e}")

        print(f"\n{SEP}")
        print(f"[2] POST 방식 테스트")
        try:
            async with sess.post(SEARCH_URL, data=SEARCH_PARAMS) as r:
                ct = r.content_type or ""
                text = await r.text(errors="replace")
                print(f"  상태: {r.status}, Content-Type: {ct}")
                print(f"  길이: {len(text)}자")
                print(f"  앞 600자:\n{text[:600]}")
        except Exception as e:
            print(f"  오류: {e}")

        print(f"\n{SEP}")
        print(f"[3] 전체 열차 (selGoTrain=109)")
        params2 = {**SEARCH_PARAMS, "selGoTrain": "109"}
        try:
            async with sess.get(SEARCH_URL, params=params2) as r:
                ct = r.content_type or ""
                text = await r.text(errors="replace")
                print(f"  상태: {r.status}, Content-Type: {ct}")
                print(f"  길이: {len(text)}자")
                if "json" in ct or text.strip()[:1] in "{[":
                    try:
                        d = json.loads(text)
                        trn_infos = d.get("trn_infos", {})
                        if trn_infos:
                            trains = trn_infos.get("trn_info", [])
                            print(f"  열차 수: {len(trains)}개")
                            for t in trains[:3]:
                                print(f"    {t.get('h_trn_clsf_nm','')} {t.get('h_trn_no','')} "
                                      f"출발:{t.get('h_dpt_tm','')} 도착:{t.get('h_arv_tm','')} "
                                      f"일반:{t.get('h_rsv_psb_nm','')} 특실:{t.get('h_spe_rsv_psb_nm','')}")
                    except json.JSONDecodeError as e:
                        print(f"  JSON 파싱 실패: {e}")
        except Exception as e:
            print(f"  오류: {e}")

    print("\n" + "=" * 60)
    print("테스트 완료")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

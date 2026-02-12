# coding: utf-8
"""
코레일 신 API 심층 탐색
실행: py -X utf8 debug_api3.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import asyncio, re, json
import aiohttp

SEP = "-" * 60
BASE = "https://www.korail.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
JSON_HEADERS = {**HEADERS, "Accept": "application/json, */*",
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}

SEARCH_FORM = {
    "txtGoStart": "서울", "txtGoEnd": "부산",
    "txtGoAbrdDt": "20260310", "txtGoHour": "080000",
    "selGoTrain": "100", "txtSeatAttCd": "015",
    "txtPsgFlg_1": "1", "txtTotPsgCnt": "1",
    "txtSeatAttCd_2": "000", "txtSeatAttCd_3": "000",
    "txtSeatAttCd_4": "015", "radioJobId": "1", "txtMenuId": "11",
}


async def fetch(session, url, method="GET", params=None, data=None, label=""):
    try:
        kwargs = {"allow_redirects": True}
        if params: kwargs["params"] = params
        if data:   kwargs["data"] = data
        fn = session.get if method == "GET" else session.post
        async with fn(url, **kwargs) as r:
            text = await r.text(errors="replace")
            is_json = "json" in (r.content_type or "") or text.strip()[:1] in "{["
            print(f"  {r.status} [{'JSON' if is_json else 'HTML'}] {label or url[:70]}")
            if r.status == 200:
                print(f"  길이: {len(text)}자")
                print(f"  앞 800자:\n{text[:800]}")
                # JSON이면 키 출력
                if is_json:
                    try:
                        d = json.loads(text)
                        print(f"  JSON 키: {list(d.keys()) if isinstance(d, dict) else type(d)}")
                    except: pass
            return text, r.status
    except Exception as e:
        print(f"  ERR {label or url[:60]}: {e}")
    return "", 0


async def main():
    print("=" * 60)
    print("코레일 신 API 심층 탐색")
    print("=" * 60)

    timeout = aiohttp.ClientTimeout(total=15, connect=8)

    async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:

        # ── 1. dynaPath.do 응답 확인 ─────────────────────────────
        print(f"\n{SEP}")
        print("[1] dynaPath.do 응답 확인")
        await fetch(session, f"{BASE}/dynaPath.do", params=SEARCH_FORM, label="dynaPath.do + params")

        # ── 2. 티켓 검색 페이지 탐색 ──────────────────────────────
        print(f"\n{SEP}")
        print("[2] 예매 관련 페이지 접근")
        pages = [
            "/ticket/search",
            "/reservation",
            "/ebizprd/EbizPrdTrnInfoList0090.do",
            "/ticket",
        ]
        for path in pages:
            await fetch(session, f"{BASE}{path}", label=path)

        # ── 3. POST 방식으로 dynaPath 시도 ──────────────────────
        print(f"\n{SEP}")
        print("[3] dynaPath.do POST 시도")

    async with aiohttp.ClientSession(headers=JSON_HEADERS, timeout=timeout) as sess2:
        post_payloads = [
            {**SEARCH_FORM, "strCmd": "getTrnList"},
            {**SEARCH_FORM, "menuid": "11"},
        ]
        for payload in post_payloads:
            await fetch(sess2, f"{BASE}/dynaPath.do", method="POST", data=payload,
                        label=f"POST dynaPath strCmd={payload.get('strCmd','')}")

        # ── 4. 실제 브라우저가 쓰는 경로 시도 (Referer 포함) ────
        print(f"\n{SEP}")
        print("[4] Referer 헤더 포함 API 시도")
        ref_headers = {**JSON_HEADERS, "Referer": f"{BASE}/ticket/search"}
        async with aiohttp.ClientSession(headers=ref_headers, timeout=timeout) as sess3:
            api_tries = [
                (f"{BASE}/ebizprd/EbizPrdSttnKeyListBy498.do", "GET"),
                (f"{BASE}/ebizprd/EbizPrdTrnInfoList0090.do", "GET"),
                (f"{BASE}/ticket/search/list", "POST"),
                (f"{BASE}/api/ticket/list", "GET"),
            ]
            for url, method in api_tries:
                await fetch(sess3, url,
                            method=method,
                            params=SEARCH_FORM if method == "GET" else None,
                            data=SEARCH_FORM if method == "POST" else None,
                            label=f"{method} {url[len(BASE):]}")

    print("\n" + "=" * 60)
    print("탐색 완료")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

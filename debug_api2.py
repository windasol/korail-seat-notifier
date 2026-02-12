# coding: utf-8
"""
코레일 신 API 탐색 스크립트
실행: py -X utf8 debug_api2.py
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import asyncio
import json
import re
import aiohttp

SEP = "-" * 60

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# ─── 1. 홈페이지에서 API 힌트 추출 ──────────────────────────────
async def scan_homepage(session: aiohttp.ClientSession) -> list[str]:
    print("\n[1] korail.com 홈 소스 스캔")
    found = []
    try:
        async with session.get("https://www.korail.com/", allow_redirects=True) as r:
            text = await r.text(errors="replace")
            print(f"    홈 상태: {r.status}, 길이: {len(text)}자")

            # JS 번들 URL 찾기
            js_urls = re.findall(r'src="(/[^"]+\.js)"', text)
            print(f"    JS 번들 {len(js_urls)}개 발견: {js_urls[:5]}")

            # inline에서 API 경로 패턴 찾기
            api_hints = re.findall(r'["\'](/[a-zA-Z0-9/_\-]+\.do)["\']', text)
            api_hints += re.findall(r'["\'](/api/[a-zA-Z0-9/_\-]+)["\']', text)
            for h in set(api_hints):
                print(f"    힌트: {h}")
                found.append(h)

            # JS 번들 하나 분석 (가장 큰 것)
            if js_urls:
                for js_url in js_urls[:3]:
                    full_url = f"https://www.korail.com{js_url}"
                    async with session.get(full_url) as jr:
                        jtext = await jr.text(errors="replace")
                        # API 경로 패턴 추출
                        patterns = re.findall(r'["\']([/a-zA-Z0-9_\-]+\.do)["\']', jtext)
                        patterns += re.findall(r'["\](/api/[a-zA-Z0-9/_\-]+)["\']', jtext)
                        unique = list(set(patterns))[:30]
                        if unique:
                            print(f"\n    JS ({js_url}) 에서 발견한 .do 경로 ({len(unique)}개):")
                            for p in sorted(unique):
                                print(f"      {p}")
                            found.extend(unique)
    except Exception as e:
        print(f"    오류: {e}")
    return found

# ─── 2. 알려진 신 API 후보 직접 테스트 ───────────────────────────
KNOWN_CANDIDATES = [
    # 코레일 신 API (커뮤니티/깃허브에서 발견된 패턴)
    "https://www.korail.com/ebizprd/EbizPrdTrnInfoList0090.do",
    "https://www.korail.com/ebizprd/prdTicketSearchList.do",
    "https://www.korail.com/api/ticket/search",
    "https://www.korail.com/api/v1/ticket/list",
    "https://www.korail.com/reservation/information",
    # 모바일 API
    "https://m.korail.com/ebizprd/EbizPrdSttnKeyListBy498.do",
    # 구 letskorail (혹시 다른 경로)
    "https://www.letskorail.com/ebizprd/EbizPrdTrnInfoList0090.do",
]

SEARCH_PARAMS = {
    "txtGoStart": "서울",
    "txtGoEnd": "부산",
    "txtGoAbrdDt": "20260310",
    "txtGoHour": "080000",
    "selGoTrain": "100",
    "txtSeatAttCd": "015",
    "txtPsgFlg_1": "1",
    "txtTotPsgCnt": "1",
    "txtMenuId": "11",
    "radioJobId": "1",
}

async def test_endpoint(session: aiohttp.ClientSession, url: str) -> bool:
    try:
        async with session.get(url, params=SEARCH_PARAMS, allow_redirects=True) as r:
            ct = r.content_type or ""
            text = await r.text(errors="replace")
            is_json = "json" in ct or (text.strip().startswith("{") or text.strip().startswith("["))
            marker = "JSON" if is_json else "HTML"
            print(f"  {r.status} [{marker}] {url[:80]}")
            if is_json and r.status == 200:
                print(f"    >> 응답 앞 300자: {text[:300]}")
                return True
            if r.status == 200 and "trn" in text.lower():
                print(f"    >> 열차 관련 키워드 포함! 앞 300자: {text[:300]}")
    except Exception as e:
        print(f"  ERR {url[:60]}: {e}")
    return False

async def main() -> None:
    print("=" * 60)
    print("코레일 신 API 탐색")
    print("=" * 60)

    timeout = aiohttp.ClientTimeout(total=12, connect=6)
    async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:
        # 홈 소스 스캔
        hints = await scan_homepage(session)

        # 알려진 후보 테스트
        print("\n[2] 알려진 후보 엔드포인트 테스트:")
        for url in KNOWN_CANDIDATES:
            await test_endpoint(session, url)

        # 홈에서 발견한 힌트 테스트
        if hints:
            print("\n[3] 홈 소스에서 발견한 경로 테스트:")
            tested = set()
            for path in hints[:20]:
                url = f"https://www.korail.com{path}" if path.startswith("/") else path
                if url not in tested:
                    tested.add(url)
                    await test_endpoint(session, url)

    print("\n" + "=" * 60)
    print("탐색 완료")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

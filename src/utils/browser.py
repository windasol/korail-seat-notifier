"""Windows 브라우저 열기 유틸리티

우선순위:
  1. Chrome 실행파일 직접 실행 (고정 경로 + LOCALAPPDATA)
  2. Windows cmd /c start (exe 환경 포함 모든 Windows 환경에서 동작)
  3. webbrowser.open_new_tab (Python stdlib 최후 fallback)
"""

from __future__ import annotations

import logging
import os
import subprocess
import webbrowser

logger = logging.getLogger("korail.browser")

_STATIC_CHROME_PATHS: tuple[str, ...] = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


def _get_chrome_paths() -> tuple[str, ...]:
    """Chrome 후보 경로 목록 (LOCALAPPDATA 동적 경로 포함)"""
    localappdata = os.environ.get("LOCALAPPDATA", "")
    dynamic = (
        os.path.join(localappdata, "Google", "Chrome", "Application", "chrome.exe")
        if localappdata
        else ""
    )
    return _STATIC_CHROME_PATHS + ((dynamic,) if dynamic else ())


def open_url(url: str) -> bool:
    """URL을 Chrome 우선, 기본 브라우저 fallback으로 열기.

    Returns:
        True  — 성공적으로 실행 요청
        False — 모든 방법 실패
    """
    # ── 1. Chrome 직접 실행 ───────────────────────────────────────
    for path in _get_chrome_paths():
        if os.path.isfile(path):
            try:
                subprocess.Popen([path, url])
                logger.info("Chrome으로 URL 열기: %s", url)
                return True
            except OSError:
                continue

    # ── 2. Windows cmd /c start (기본 브라우저, exe 포함) ──────────
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("cmd start로 URL 열기: %s", url)
        return True
    except OSError:
        pass

    # ── 3. webbrowser stdlib fallback ─────────────────────────────
    try:
        webbrowser.open_new_tab(url)
        logger.info("webbrowser로 URL 열기: %s", url)
        return True
    except Exception as exc:
        logger.error("URL 열기 실패 (모든 방법 소진): %s", exc)
        return False

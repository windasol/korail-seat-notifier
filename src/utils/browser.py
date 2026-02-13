"""Windows 브라우저 열기 유틸리티

우선순위:
  1. Chrome 실행파일 직접 실행 (고정 경로 + LOCALAPPDATA)
  2. Windows cmd /c start (exe 환경 포함 모든 Windows 환경에서 동작)
  3. webbrowser.open_new_tab (Python stdlib 최후 fallback)
"""

from __future__ import annotations

import ctypes
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

    우선순위:
      1. Chrome 실행파일 직접 실행
      2. ctypes ShellExecuteW — Win32 API 직접 호출 (exe 환경 포함, & 문제 없음)
      3. os.startfile — Python wrapper for ShellExecute
      4. webbrowser.open_new_tab — stdlib 최후 fallback

    Returns:
        True  — 성공적으로 실행 요청
        False — 모든 방법 실패
    """
    logger.info("URL 열기 시도: %s", url)

    # ── 1. Chrome 직접 실행 ───────────────────────────────────────
    for path in _get_chrome_paths():
        if os.path.isfile(path):
            try:
                subprocess.Popen([path, url])
                logger.info("성공 [Chrome]: %s", path)
                return True
            except OSError as e:
                logger.debug("Chrome Popen 실패 (%s): %s", path, e)
                continue

    # ── 2. ctypes ShellExecuteW (exe 포함 가장 신뢰성 높음) ────────
    try:
        result = ctypes.windll.shell32.ShellExecuteW(None, "open", url, None, None, 1)  # type: ignore[attr-defined]
        if result > 32:
            logger.info("성공 [ctypes ShellExecuteW]: result=%d", result)
            return True
        logger.warning("ShellExecuteW 반환값 이상: %d", result)
    except Exception as e:
        logger.debug("ctypes ShellExecuteW 실패: %s", e)

    # ── 3. os.startfile ───────────────────────────────────────────
    try:
        os.startfile(url)  # type: ignore[attr-defined]
        logger.info("성공 [os.startfile]")
        return True
    except (AttributeError, OSError) as e:
        logger.debug("os.startfile 실패: %s", e)

    # ── 4. webbrowser stdlib fallback ─────────────────────────────
    try:
        webbrowser.open_new_tab(url)
        logger.info("성공 [webbrowser]")
        return True
    except Exception as exc:
        logger.error("URL 열기 실패 (모든 방법 소진): %s", exc)
        return False

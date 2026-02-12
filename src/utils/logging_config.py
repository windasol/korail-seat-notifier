"""로깅 설정

콘솔 + 파일 로깅을 구성한다.
컬러 출력과 한국어 시간대를 지원.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


# ANSI 컬러 코드 (Windows Terminal / modern terminals 지원)
_COLORS = {
    "DEBUG": "\033[36m",     # Cyan
    "INFO": "\033[32m",      # Green
    "WARNING": "\033[33m",   # Yellow
    "ERROR": "\033[31m",     # Red
    "CRITICAL": "\033[35m",  # Magenta
    "RESET": "\033[0m",
}


class ColorFormatter(logging.Formatter):
    """컬러 로그 포매터"""

    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, "")
        reset = _COLORS["RESET"]
        record.levelname = f"{color}{record.levelname:<8}{reset}"
        return super().format(record)


def setup_logging(
    level: str = "INFO",
    log_file: str | Path | None = None,
) -> None:
    """로깅 초기화

    Args:
        level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
        log_file: 로그 파일 경로 (None이면 콘솔만)
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 기존 핸들러 제거
    root.handlers.clear()

    # 콘솔 핸들러
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ColorFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s │ %(message)s",
        datefmt="%H:%M:%S",
    ))
    root.addHandler(console)

    # 파일 핸들러 (선택)
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root.addHandler(fh)

    # aiohttp 내부 로그 레벨 조정
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    # Windows에서 ANSI 컬러 활성화
    _enable_windows_ansi()


def _enable_windows_ansi() -> None:
    """Windows 터미널에서 ANSI escape 시퀀스 활성화"""
    try:
        import platform
        if platform.system() != "Windows":
            return
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass

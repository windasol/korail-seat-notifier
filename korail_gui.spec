# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Korail Seat Notifier GUI
빌드 명령: pyinstaller korail_gui.spec
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "run_gui.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "aiohttp",
        "aiohttp.client",
        "aiohttp.connector",
        "aiohttp.resolver",
        "aiohttp.streams",
        "asyncio",
        "tkinter",
        "tkinter.ttk",
        "tkinter.scrolledtext",
        "tkinter.messagebox",
        "winsound",
        "winotify",
        "src",
        "src.gui",
        "src.main",
        "src.agents",
        "src.agents.orchestrator",
        "src.agents.monitor_agent",
        "src.agents.notifier_agent",
        "src.agents.health_agent",
        "src.agents.input_agent",
        "src.agents.base",
        "src.models",
        "src.models.config",
        "src.models.events",
        "src.models.query",
        "src.skills",
        "src.skills.seat_checker",
        "src.skills.notifier",
        "src.skills.poller",
        "src.skills.station_data",
        "src.skills.validation",
        "src.skills.parser",
        "src.skills.base",
        "src.utils",
        "src.utils.rate_limiter",
        "src.utils.logging_config",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest", "mypy", "ruff",
        "matplotlib", "numpy", "pandas",
        "PIL", "cv2",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="코레일_빈자리알림",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # GUI 앱: 콘솔 창 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
    icon=None,
)

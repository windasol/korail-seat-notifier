"""코레일 좌석 빈자리 알림 - GUI 애플리케이션

tkinter 기반 GUI. OrchestratorAgent를 백그라운드 스레드(asyncio)에서 실행하고
로그와 상태를 메인 스레드(GUI)에 안전하게 전달한다.
"""

from __future__ import annotations

import asyncio
import logging
import os
import queue
import threading
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import messagebox, scrolledtext, ttk
from typing import Optional

from src.agents.orchestrator import OrchestratorAgent, OrchestratorState
from src.models.config import AgentConfig
from src.models.query import TrainQuery
from src.skills.station_data import STATION_CODES, validate_station

# ── 색상 팔레트 ──────────────────────────────────────────────────
CLR_BG        = "#F5F6FA"
CLR_PANEL     = "#FFFFFF"
CLR_BORDER    = "#DDE1EA"
CLR_ACCENT    = "#003DA5"   # 코레일 블루
CLR_ACCENT_HV = "#0051CC"
CLR_SUCCESS   = "#1A7F4B"
CLR_WARN      = "#E07B00"
CLR_ERROR     = "#C0392B"
CLR_TEXT      = "#1A1D23"
CLR_MUTED     = "#6B7280"
CLR_LOG_BG    = "#1E2130"
CLR_LOG_FG    = "#E2E8F0"

STATIONS = sorted(STATION_CODES.keys())
TRAIN_TYPES = ["KTX", "KTX-산천", "KTX-이음", "ITX-새마을", "ITX-청춘", "무궁화", "전체"]
SEAT_TYPES = ["일반실", "특실"]
FONT_TITLE  = ("Malgun Gothic", 15, "bold")
FONT_LABEL  = ("Malgun Gothic", 10)
FONT_BOLD   = ("Malgun Gothic", 10, "bold")
FONT_LOG    = ("Consolas", 9)
FONT_STATUS = ("Malgun Gothic", 11, "bold")


# ─────────────────────────────────────────────────────────────────
# 로깅 핸들러 : asyncio 스레드 → GUI 큐 전달
# ─────────────────────────────────────────────────────────────────

class QueueLogHandler(logging.Handler):
    """로그 레코드를 스레드-세이프 큐에 넣는 핸들러"""

    def __init__(self, log_queue: queue.Queue) -> None:  # type: ignore[type-arg]
        super().__init__()
        self._q = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._q.put_nowait(("log", record.levelno, msg))
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────
# 비동기 실행기 : 별도 스레드에서 asyncio 루프 운영
# ─────────────────────────────────────────────────────────────────

class AsyncRunner:
    """GUI 스레드와 독립된 asyncio 이벤트 루프 관리"""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="AsyncLoop"
        )
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def submit(self, coro) -> asyncio.Future:  # type: ignore[type-arg]
        """코루틴을 비동기 루프에 제출하고 Future 반환"""
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def call_soon(self, callback) -> None:  # type: ignore[type-arg]
        """루프 스레드에서 콜백 실행"""
        self._loop.call_soon_threadsafe(callback)

    def stop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)


# ─────────────────────────────────────────────────────────────────
# 메인 GUI 클래스
# ─────────────────────────────────────────────────────────────────

class KorailGUI:
    """코레일 좌석 알림 GUI"""

    POLL_INTERVAL_MS = 100  # GUI 업데이트 주기 (ms)

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._gui_queue: queue.Queue = queue.Queue()  # type: ignore[type-arg]
        self._async_runner = AsyncRunner()
        self._orchestrator: Optional[OrchestratorAgent] = None
        self._monitor_future: Optional[asyncio.Future] = None  # type: ignore[type-arg]
        self._is_monitoring = False

        self._setup_logging()
        self._build_ui()
        self._start_queue_poll()

    # ── 로깅 설정 ─────────────────────────────────────────────────

    def _setup_logging(self) -> None:
        """korail.* 로거를 GUI 큐 핸들러로 연결"""
        handler = QueueLogHandler(self._gui_queue)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        root_logger = logging.getLogger("korail")
        root_logger.setLevel(logging.INFO)
        root_logger.handlers.clear()
        root_logger.addHandler(handler)

    # ── UI 구성 ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._root.title("코레일 좌석 빈자리 알림 v2.0")
        self._root.configure(bg=CLR_BG)
        self._root.resizable(False, False)

        # 중앙 정렬
        w, h = 660, 750
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        self._root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        # 스타일
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", padding=5, font=FONT_LABEL)
        style.configure("TSpinbox", padding=5, font=FONT_LABEL)
        style.configure("TEntry", padding=5, font=FONT_LABEL)
        style.configure("TCheckbutton", background=CLR_PANEL,
                        font=FONT_LABEL, foreground=CLR_TEXT)

        main = tk.Frame(self._root, bg=CLR_BG, padx=16, pady=12)
        main.pack(fill=tk.BOTH, expand=True)

        # 타이틀
        self._build_title(main)
        # 구간 입력
        self._build_route_section(main)
        # 날짜/열차 입력
        self._build_detail_section(main)
        # 시간 범위
        self._build_time_section(main)
        # 알림 설정
        self._build_notify_section(main)
        # 버튼
        self._build_buttons(main)
        # 상태 표시
        self._build_status(main)
        # 로그
        self._build_log(main)

    # ── 타이틀 ────────────────────────────────────────────────────

    def _build_title(self, parent: tk.Frame) -> None:
        frame = tk.Frame(parent, bg=CLR_ACCENT, pady=10)
        frame.pack(fill=tk.X, pady=(0, 12))
        tk.Label(
            frame,
            text="🚄  코레일 좌석 빈자리 알림",
            font=FONT_TITLE,
            bg=CLR_ACCENT, fg="white",
        ).pack()

    # ── 구간 선택 ─────────────────────────────────────────────────

    def _build_route_section(self, parent: tk.Frame) -> None:
        panel = self._panel(parent, "🗺  출발 · 도착역")

        frame = tk.Frame(panel, bg=CLR_PANEL)
        frame.pack(fill=tk.X, padx=12, pady=(0, 10))
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(4, weight=1)

        # 출발역
        tk.Label(frame, text="출발역", font=FONT_BOLD,
                 bg=CLR_PANEL, fg=CLR_TEXT).grid(row=0, column=0, padx=(0, 6), sticky="w")
        self._dep_var = tk.StringVar(value="서울")
        dep_cb = ttk.Combobox(frame, textvariable=self._dep_var,
                               values=STATIONS, state="readonly", width=14)
        dep_cb.grid(row=0, column=1, sticky="ew")

        # 화살표
        tk.Label(frame, text="→", font=("Malgun Gothic", 14, "bold"),
                 bg=CLR_PANEL, fg=CLR_ACCENT).grid(row=0, column=2, padx=12)

        # 도착역
        tk.Label(frame, text="도착역", font=FONT_BOLD,
                 bg=CLR_PANEL, fg=CLR_TEXT).grid(row=0, column=3, padx=(0, 6), sticky="w")
        self._arr_var = tk.StringVar(value="부산")
        arr_cb = ttk.Combobox(frame, textvariable=self._arr_var,
                               values=STATIONS, state="readonly", width=14)
        arr_cb.grid(row=0, column=4, sticky="ew")

    # ── 날짜/열차/좌석/인원 ───────────────────────────────────────

    def _build_detail_section(self, parent: tk.Frame) -> None:
        panel = self._panel(parent, "📋  상세 조건")

        frame = tk.Frame(panel, bg=CLR_PANEL)
        frame.pack(fill=tk.X, padx=12, pady=(0, 10))

        # 날짜
        tk.Label(frame, text="출발 날짜", font=FONT_BOLD,
                 bg=CLR_PANEL, fg=CLR_TEXT).grid(row=0, column=0, sticky="w", padx=(0, 6))
        tomorrow = date.today() + timedelta(days=1)
        self._date_var = tk.StringVar(value=tomorrow.strftime("%Y-%m-%d"))
        date_entry = ttk.Entry(frame, textvariable=self._date_var, width=13)
        date_entry.grid(row=0, column=1, padx=(0, 16), sticky="ew")

        # 열차 종류
        tk.Label(frame, text="열차", font=FONT_BOLD,
                 bg=CLR_PANEL, fg=CLR_TEXT).grid(row=0, column=2, sticky="w", padx=(0, 6))
        self._train_var = tk.StringVar(value="KTX")
        ttk.Combobox(frame, textvariable=self._train_var,
                     values=TRAIN_TYPES, state="readonly", width=11).grid(
            row=0, column=3, padx=(0, 16), sticky="ew")

        # 좌석 유형
        tk.Label(frame, text="좌석", font=FONT_BOLD,
                 bg=CLR_PANEL, fg=CLR_TEXT).grid(row=0, column=4, sticky="w", padx=(0, 6))
        self._seat_var = tk.StringVar(value="일반실")
        ttk.Combobox(frame, textvariable=self._seat_var,
                     values=SEAT_TYPES, state="readonly", width=8).grid(
            row=0, column=5, padx=(0, 16), sticky="ew")

        # 승객 수
        tk.Label(frame, text="승객", font=FONT_BOLD,
                 bg=CLR_PANEL, fg=CLR_TEXT).grid(row=0, column=6, sticky="w", padx=(0, 6))
        self._pax_var = tk.StringVar(value="1")
        ttk.Spinbox(frame, textvariable=self._pax_var,
                    from_=1, to=9, width=4).grid(row=0, column=7, sticky="ew")

    # ── 시간 범위 ─────────────────────────────────────────────────

    def _build_time_section(self, parent: tk.Frame) -> None:
        panel = self._panel(parent, "⏰  희망 탑승 시간대")

        frame = tk.Frame(panel, bg=CLR_PANEL)
        frame.pack(fill=tk.X, padx=12, pady=(0, 10))

        def time_spinboxes(label: str, col: int, h_var: tk.StringVar, m_var: tk.StringVar) -> None:
            tk.Label(frame, text=label, font=FONT_BOLD,
                     bg=CLR_PANEL, fg=CLR_TEXT).grid(row=0, column=col, sticky="w", padx=(0, 6))
            ttk.Spinbox(frame, textvariable=h_var, from_=0, to=23,
                        width=4, format="%02.0f").grid(row=0, column=col+1)
            tk.Label(frame, text=":", font=FONT_BOLD, bg=CLR_PANEL,
                     fg=CLR_TEXT).grid(row=0, column=col+2)
            ttk.Spinbox(frame, textvariable=m_var, from_=0, to=59,
                        width=4, format="%02.0f").grid(row=0, column=col+3)

        self._start_h = tk.StringVar(value="08")
        self._start_m = tk.StringVar(value="00")
        self._end_h   = tk.StringVar(value="12")
        self._end_m   = tk.StringVar(value="00")

        time_spinboxes("시작", 0, self._start_h, self._start_m)
        tk.Label(frame, text="  ~  ", font=FONT_LABEL,
                 bg=CLR_PANEL, fg=CLR_MUTED).grid(row=0, column=4)
        time_spinboxes("종료", 5, self._end_h, self._end_m)

    # ── 알림 설정 ─────────────────────────────────────────────────

    def _build_notify_section(self, parent: tk.Frame) -> None:
        panel = self._panel(parent, "🔔  알림 설정")

        frame = tk.Frame(panel, bg=CLR_PANEL)
        frame.pack(fill=tk.X, padx=12, pady=(0, 10))

        self._notify_desktop = tk.BooleanVar(value=True)
        self._notify_sound   = tk.BooleanVar(value=True)
        self._notify_webhook = tk.BooleanVar(value=False)

        ttk.Checkbutton(frame, text="데스크톱 알림",
                        variable=self._notify_desktop).grid(row=0, column=0, padx=(0, 16))
        ttk.Checkbutton(frame, text="소리 알림",
                        variable=self._notify_sound).grid(row=0, column=1, padx=(0, 16))
        ttk.Checkbutton(frame, text="Webhook",
                        variable=self._notify_webhook).grid(row=0, column=2, padx=(0, 16))

        # 조회 간격
        tk.Label(frame, text="조회 간격 (초):", font=FONT_LABEL,
                 bg=CLR_PANEL, fg=CLR_TEXT).grid(row=0, column=3, padx=(24, 6))
        self._interval_var = tk.StringVar(value="30")
        ttk.Spinbox(frame, textvariable=self._interval_var,
                    from_=30, to=300, increment=10, width=5).grid(row=0, column=4)

    # ── 버튼 ──────────────────────────────────────────────────────

    def _build_buttons(self, parent: tk.Frame) -> None:
        frame = tk.Frame(parent, bg=CLR_BG, pady=8)
        frame.pack(fill=tk.X)

        # 시작 버튼
        self._btn_start = tk.Button(
            frame,
            text="▶  모니터링 시작",
            font=FONT_BOLD,
            bg=CLR_ACCENT, fg="white",
            activebackground=CLR_ACCENT_HV, activeforeground="white",
            relief=tk.FLAT, padx=24, pady=10,
            cursor="hand2",
            command=self._on_start,
        )
        self._btn_start.pack(side=tk.LEFT, padx=(0, 10))

        # 중지 버튼
        self._btn_stop = tk.Button(
            frame,
            text="■  중지",
            font=FONT_BOLD,
            bg=CLR_ERROR, fg="white",
            activebackground="#A93226", activeforeground="white",
            relief=tk.FLAT, padx=24, pady=10,
            cursor="hand2",
            state=tk.DISABLED,
            command=self._on_stop,
        )
        self._btn_stop.pack(side=tk.LEFT, padx=(0, 10))

        # 로그 지우기
        tk.Button(
            frame,
            text="🗑  로그 지우기",
            font=FONT_LABEL,
            bg=CLR_BORDER, fg=CLR_TEXT,
            activebackground=CLR_MUTED, activeforeground="white",
            relief=tk.FLAT, padx=12, pady=10,
            cursor="hand2",
            command=self._clear_log,
        ).pack(side=tk.RIGHT)

    # ── 상태 표시 ─────────────────────────────────────────────────

    def _build_status(self, parent: tk.Frame) -> None:
        frame = tk.Frame(parent, bg=CLR_PANEL,
                         relief=tk.FLAT, bd=1, pady=8)
        frame.pack(fill=tk.X, pady=(0, 8))
        frame.configure(highlightbackground=CLR_BORDER, highlightthickness=1)

        inner = tk.Frame(frame, bg=CLR_PANEL)
        inner.pack(padx=12)

        self._status_dot = tk.Label(inner, text="●", font=("Arial", 14),
                                     bg=CLR_PANEL, fg=CLR_MUTED)
        self._status_dot.pack(side=tk.LEFT, padx=(0, 8))

        self._status_label = tk.Label(inner, text="대기 중",
                                       font=FONT_STATUS, bg=CLR_PANEL, fg=CLR_MUTED)
        self._status_label.pack(side=tk.LEFT)

        # 요청 카운터
        self._counter_label = tk.Label(frame, text="", font=FONT_LABEL,
                                        bg=CLR_PANEL, fg=CLR_MUTED)
        self._counter_label.pack(side=tk.RIGHT, padx=12)

    # ── 로그 영역 ─────────────────────────────────────────────────

    def _build_log(self, parent: tk.Frame) -> None:
        frame = tk.Frame(parent, bg=CLR_BG)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="📋  실시간 로그",
                 font=FONT_BOLD, bg=CLR_BG, fg=CLR_TEXT).pack(anchor="w")

        self._log_text = scrolledtext.ScrolledText(
            frame,
            font=FONT_LOG,
            bg=CLR_LOG_BG, fg=CLR_LOG_FG,
            insertbackground="white",
            relief=tk.FLAT,
            wrap=tk.WORD,
            height=14,
            state=tk.DISABLED,
        )
        self._log_text.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        # 로그 레벨별 색상 태그
        self._log_text.tag_configure("INFO",    foreground="#93C5FD")
        self._log_text.tag_configure("WARNING", foreground="#FCD34D")
        self._log_text.tag_configure("ERROR",   foreground="#F87171")
        self._log_text.tag_configure("SUCCESS", foreground="#6EE7B7")
        self._log_text.tag_configure("DETECT",  foreground="#F9A825",
                                      font=(*FONT_LOG[:2], "bold"))

    # ── 유틸 ──────────────────────────────────────────────────────

    def _panel(self, parent: tk.Frame, title: str) -> tk.Frame:
        """테두리 있는 섹션 패널 생성"""
        outer = tk.Frame(parent, bg=CLR_BG, pady=4)
        outer.pack(fill=tk.X)
        tk.Label(outer, text=title, font=FONT_BOLD,
                 bg=CLR_BG, fg=CLR_ACCENT).pack(anchor="w", pady=(0, 4))
        inner = tk.Frame(outer, bg=CLR_PANEL, pady=10,
                         highlightbackground=CLR_BORDER, highlightthickness=1)
        inner.pack(fill=tk.X)
        return inner

    def _log(self, msg: str, tag: str = "INFO") -> None:
        """GUI 로그 텍스트에 한 줄 추가 (메인 스레드에서 호출)"""
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.insert(tk.END, msg + "\n", tag)
        self._log_text.configure(state=tk.DISABLED)
        self._log_text.see(tk.END)

    def _clear_log(self) -> None:
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.configure(state=tk.DISABLED)

    def _set_status(self, text: str, color: str) -> None:
        self._status_dot.configure(fg=color)
        self._status_label.configure(text=text, fg=color)

    # ── 큐 폴링 (GUI 업데이트) ────────────────────────────────────

    def _start_queue_poll(self) -> None:
        self._poll_queue()

    def _poll_queue(self) -> None:
        """비동기 스레드로부터 메시지를 읽어 GUI 업데이트"""
        try:
            while True:
                item = self._gui_queue.get_nowait()
                kind = item[0]

                if kind == "log":
                    _, level, msg = item
                    if level >= logging.ERROR:
                        tag = "ERROR"
                    elif level >= logging.WARNING:
                        tag = "WARNING"
                    elif "빈자리 발견" in msg or "DETECT" in msg:
                        tag = "DETECT"
                    else:
                        tag = "INFO"
                    self._log(msg, tag)

                elif kind == "status":
                    _, text, color = item
                    self._set_status(text, color)

                elif kind == "counter":
                    _, text = item
                    self._counter_label.configure(text=text)

                elif kind == "done":
                    self._on_monitoring_done()

                elif kind == "seat_found":
                    self._on_seat_found()

        except queue.Empty:
            pass

        self._root.after(self.POLL_INTERVAL_MS, self._poll_queue)

    # ── 이벤트 핸들러 ─────────────────────────────────────────────

    def _on_start(self) -> None:
        """모니터링 시작"""
        try:
            query = self._build_query()
            config = self._build_config()
        except ValueError as e:
            messagebox.showerror("입력 오류", str(e))
            return

        self._is_monitoring = True
        self._btn_start.configure(state=tk.DISABLED)
        self._btn_stop.configure(state=tk.NORMAL)
        self._set_status("모니터링 중...", CLR_ACCENT)
        self._gui_queue.put(("counter", ""))

        summary = (
            f"\n{'─'*52}\n"
            f"  🚄 모니터링 시작\n"
            f"  구간: {query.departure_station} → {query.arrival_station}\n"
            f"  날짜: {query.departure_date}  "
            f"시간: {query.preferred_time_start:%H:%M}~{query.preferred_time_end:%H:%M}\n"
            f"  열차: {query.train_type}  좌석: {query.seat_type}  "
            f"승객: {query.passenger_count}명\n"
            f"  조회 간격: {config.base_interval:.0f}초\n"
            f"{'─'*52}"
        )
        self._log(summary, "SUCCESS")

        self._orchestrator = OrchestratorAgent(config)
        self._monitor_future = self._async_runner.submit(
            self._run_monitoring(query, config)
        )

    def _on_stop(self) -> None:
        """모니터링 중지"""
        if self._orchestrator:
            self._orchestrator.stop()
            self._log("\n  ■ 중지 요청 전송됨...", "WARNING")

    def _on_monitoring_done(self) -> None:
        """모니터링 종료 후 UI 복원"""
        self._is_monitoring = False
        self._btn_start.configure(state=tk.NORMAL)
        self._btn_stop.configure(state=tk.DISABLED)
        self._set_status("모니터링 종료", CLR_MUTED)
        self._counter_label.configure(text="")

    def _on_seat_found(self) -> None:
        """좌석 감지 시 상태 깜빡임 효과"""
        self._set_status("🎉 빈자리 발견!", CLR_SUCCESS)
        self._root.bell()
        # 3초 후 복원
        self._root.after(3000, lambda: self._set_status("모니터링 중...", CLR_ACCENT))

    # ── 쿼리/설정 빌더 ────────────────────────────────────────────

    def _build_query(self) -> TrainQuery:
        dep = validate_station(self._dep_var.get())
        arr = validate_station(self._arr_var.get())

        if dep == arr:
            raise ValueError("출발역과 도착역이 같습니다.")

        # 날짜 파싱
        date_str = self._date_var.get().strip().replace("-", "")
        if len(date_str) != 8:
            raise ValueError("날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)")
        dep_date = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
        if dep_date < date.today():
            raise ValueError("과거 날짜는 선택할 수 없습니다.")

        from datetime import time as dtime
        t_start = dtime(int(self._start_h.get()), int(self._start_m.get()))
        t_end   = dtime(int(self._end_h.get()), int(self._end_m.get()))
        if t_end <= t_start:
            raise ValueError("종료 시간이 시작 시간보다 커야 합니다.")

        pax = int(self._pax_var.get())
        if not (1 <= pax <= 9):
            raise ValueError("승객 수는 1~9명이어야 합니다.")

        return TrainQuery(
            departure_station=dep,
            arrival_station=arr,
            departure_date=dep_date,
            preferred_time_start=t_start,
            preferred_time_end=t_end,
            train_type=self._train_var.get(),
            seat_type=self._seat_var.get(),
            passenger_count=pax,
        )

    def _build_config(self) -> AgentConfig:
        methods: list[str] = []
        if self._notify_desktop.get():
            methods.append("desktop")
        if self._notify_sound.get():
            methods.append("sound")
        if self._notify_webhook.get():
            methods.append("webhook")

        interval = max(float(self._interval_var.get()), 30.0)

        return AgentConfig(
            base_interval=interval,
            notification_methods=methods,
            webhook_url=os.environ.get("KORAIL_WEBHOOK_URL", ""),
        )

    # ── 비동기 모니터링 루프 ──────────────────────────────────────

    async def _run_monitoring(
        self, query: TrainQuery, config: AgentConfig
    ) -> None:
        """OrchestratorAgent 실행 (비동기 스레드에서 호출)"""
        assert self._orchestrator is not None

        # 이벤트 버스 모니터링 (좌석 감지 감시)
        original_dispatch = self._orchestrator._dispatch

        async def patched_dispatch(msg):  # type: ignore[return]
            from src.models.events import AgentEvent
            if msg.event == AgentEvent.SEAT_DETECTED:
                self._gui_queue.put_nowait(("seat_found",))
            if msg.event == AgentEvent.POLL_RESULT:
                payload = msg.payload
                if isinstance(payload, dict):
                    count = payload.get("request_count", 0)
                    self._gui_queue.put_nowait(("counter", f"조회 {count}회"))
            await original_dispatch(msg)

        self._orchestrator._dispatch = patched_dispatch  # type: ignore[method-assign]

        try:
            self._gui_queue.put_nowait(("status", "모니터링 중...", CLR_ACCENT))
            await self._orchestrator.run(query)
        except Exception as e:
            self._gui_queue.put_nowait(("log", logging.ERROR, f"오류 발생: {e}"))
        finally:
            self._gui_queue.put_nowait(("done",))


# ─────────────────────────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────────────────────────

def launch() -> None:
    """GUI 실행 진입점"""
    root = tk.Tk()
    try:
        root.iconbitmap(default="")
    except Exception:
        pass
    app = KorailGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: _on_close(root, app))
    root.mainloop()


def _on_close(root: tk.Tk, app: KorailGUI) -> None:
    """창 닫기 처리: 모니터링 중이면 중지 후 종료"""
    if app._is_monitoring and app._orchestrator:
        app._orchestrator.stop()
    app._async_runner.stop()
    root.destroy()


if __name__ == "__main__":
    launch()

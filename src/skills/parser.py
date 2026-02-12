"""입력 파싱 스킬

CLI 인자와 대화형 입력을 구조화된 딕셔너리로 변환한다.
"""

from __future__ import annotations

import argparse
from datetime import date, time
from typing import Any


class ParserSkill:
    """입력 파싱 스킬"""

    @staticmethod
    def parse_cli(args: argparse.Namespace) -> dict[str, Any]:
        """CLI 인자 → dict 변환"""
        return {
            "departure": args.departure.strip() if args.departure else None,
            "arrival": args.arrival.strip() if args.arrival else None,
            "date": args.date,
            "time_start": args.time_start,
            "time_end": args.time_end,
            "train_type": getattr(args, "train_type", "KTX"),
            "seat_type": getattr(args, "seat_type", "일반실"),
            "passengers": getattr(args, "passengers", 1),
        }

    @staticmethod
    def parse_interactive(raw_inputs: dict[str, str]) -> dict[str, Any]:
        """대화형 입력 → 구조화 dict"""
        result: dict[str, Any] = {}

        dep = raw_inputs.get("departure", "").strip()
        result["departure"] = dep if dep else None

        arr = raw_inputs.get("arrival", "").strip()
        result["arrival"] = arr if arr else None

        date_str = raw_inputs.get("date", "").strip().replace("-", "")
        if date_str and len(date_str) == 8:
            result["date"] = date(
                int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8])
            )
        else:
            result["date"] = None

        for key, field in [
            ("time_start", "time_start"),
            ("time_end", "time_end"),
        ]:
            t_str = raw_inputs.get(key, "").strip().replace(":", "")
            if t_str and len(t_str) >= 4:
                result[field] = time(int(t_str[:2]), int(t_str[2:4]))
            else:
                result[field] = None

        result["train_type"] = raw_inputs.get("train_type", "KTX").strip() or "KTX"
        result["seat_type"] = raw_inputs.get("seat_type", "일반실").strip() or "일반실"

        pax = raw_inputs.get("passengers", "1").strip()
        result["passengers"] = int(pax) if pax.isdigit() else 1

        return result

    @staticmethod
    def parse_date(s: str) -> date:
        """YYYY-MM-DD 또는 YYYYMMDD → date"""
        s = s.strip().replace("-", "")
        if len(s) != 8:
            raise ValueError(f"날짜 형식 오류: '{s}' (YYYY-MM-DD)")
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))

    @staticmethod
    def parse_time(s: str) -> time:
        """HH:MM 또는 HHMM → time"""
        s = s.strip().replace(":", "")
        if len(s) < 4:
            s = s.ljust(4, "0")
        return time(int(s[:2]), int(s[2:4]))

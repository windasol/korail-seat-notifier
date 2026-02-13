"""브라우저 열기 유틸리티 단위 테스트"""

from unittest.mock import MagicMock, patch

import pytest

from src.utils.browser import _get_chrome_paths, open_url


# ─────────────────────────────────────────────────────────────────
# _get_chrome_paths
# ─────────────────────────────────────────────────────────────────

class TestGetChromePaths:
    def test_includes_static_paths(self):
        paths = _get_chrome_paths()
        assert any("Program Files" in p for p in paths)

    def test_includes_localappdata_when_set(self):
        with patch.dict("os.environ", {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}):
            paths = _get_chrome_paths()
        assert any("AppData" in p for p in paths)

    def test_no_empty_path_when_localappdata_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            # LOCALAPPDATA 없어도 빈 문자열 경로 포함 안 됨
            paths = _get_chrome_paths()
        assert all(p for p in paths)


# ─────────────────────────────────────────────────────────────────
# open_url — Chrome 직접 실행
# ─────────────────────────────────────────────────────────────────

class TestOpenUrlChrome:
    def test_chrome_found_opens_with_popen(self, tmp_path):
        chrome = tmp_path / "chrome.exe"
        chrome.write_bytes(b"")

        with patch("src.utils.browser._get_chrome_paths", return_value=(str(chrome),)):
            with patch("src.utils.browser.subprocess.Popen") as mock_popen:
                result = open_url("https://example.com")

        assert result is True
        mock_popen.assert_called_once_with([str(chrome), "https://example.com"])

    def test_chrome_popen_oserror_tries_next_path(self, tmp_path):
        chrome1 = tmp_path / "bad_chrome.exe"
        chrome2 = tmp_path / "good_chrome.exe"
        chrome1.write_bytes(b"")
        chrome2.write_bytes(b"")

        call_count = {"n": 0}

        def popen_side_effect(args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise OSError("첫 번째 크롬 실패")
            return MagicMock()

        with patch(
            "src.utils.browser._get_chrome_paths",
            return_value=(str(chrome1), str(chrome2)),
        ):
            with patch("src.utils.browser.subprocess.Popen", side_effect=popen_side_effect):
                result = open_url("https://example.com")

        assert result is True
        assert call_count["n"] == 2

    def test_chrome_file_not_exist_skipped(self, tmp_path):
        """Chrome 파일이 없으면 Popen 호출 없이 os.startfile로 넘어가야 함"""
        nonexistent = str(tmp_path / "nonexistent_chrome.exe")

        with patch("src.utils.browser._get_chrome_paths", return_value=(nonexistent,)):
            with patch("src.utils.browser.subprocess.Popen") as mock_popen:
                with patch("src.utils.browser.os.startfile") as mock_sf:
                    open_url("https://example.com")

        mock_popen.assert_not_called()
        mock_sf.assert_called_once_with("https://example.com")


# ─────────────────────────────────────────────────────────────────
# open_url — os.startfile fallback (cmd /c start 대체)
# ─────────────────────────────────────────────────────────────────

class TestOpenUrlStartfile:
    def test_no_chrome_uses_startfile(self):
        """Chrome 없으면 os.startfile 로 URL 열기"""
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.os.startfile") as mock_sf:
                result = open_url("https://example.com")

        assert result is True
        mock_sf.assert_called_once_with("https://example.com")

    def test_url_with_ampersand_safe(self):
        """& 포함 URL도 os.startfile 에 그대로 전달 (cmd 파싱 문제 없음)"""
        url = "https://www.korail.com/ticket/search?startStnCd=0001&endStnCd=0032&psgNum=1"
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.os.startfile") as mock_sf:
                open_url(url)

        mock_sf.assert_called_once_with(url)

    def test_startfile_oserror_falls_to_webbrowser(self):
        """os.startfile 실패 시 webbrowser fallback"""
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.os.startfile", side_effect=OSError):
                with patch("src.utils.browser.webbrowser.open_new_tab") as mock_wb:
                    result = open_url("https://example.com")

        assert result is True
        mock_wb.assert_called_once_with("https://example.com")

    def test_startfile_attribute_error_falls_to_webbrowser(self):
        """비-Windows에서 os.startfile 없을 때 webbrowser fallback"""
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.os.startfile", side_effect=AttributeError):
                with patch("src.utils.browser.webbrowser.open_new_tab") as mock_wb:
                    result = open_url("https://example.com")

        assert result is True
        mock_wb.assert_called_once_with("https://example.com")


# ─────────────────────────────────────────────────────────────────
# open_url — webbrowser fallback
# ─────────────────────────────────────────────────────────────────

class TestOpenUrlWebbrowser:
    def test_webbrowser_called_when_all_else_fails(self):
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.os.startfile", side_effect=OSError):
                with patch("src.utils.browser.webbrowser.open_new_tab") as mock_wb:
                    result = open_url("https://korail.com")

        assert result is True
        mock_wb.assert_called_once_with("https://korail.com")

    def test_all_methods_fail_returns_false(self):
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.os.startfile", side_effect=OSError):
                with patch(
                    "src.utils.browser.webbrowser.open_new_tab",
                    side_effect=Exception("no browser"),
                ):
                    result = open_url("https://example.com")

        assert result is False

    def test_returns_true_on_success(self):
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.os.startfile", side_effect=OSError):
                with patch("src.utils.browser.webbrowser.open_new_tab", return_value=None):
                    result = open_url("https://example.com")

        assert result is True

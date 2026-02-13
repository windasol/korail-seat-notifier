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
        nonexistent = str(tmp_path / "nonexistent_chrome.exe")

        with patch("src.utils.browser._get_chrome_paths", return_value=(nonexistent,)):
            with patch("src.utils.browser.subprocess.Popen") as mock_popen:
                with patch("src.utils.browser.webbrowser.open_new_tab"):
                    open_url("https://example.com")

        # Popen 이 Chrome 경로로 호출된 게 아니라 cmd 로 호출돼야 함
        if mock_popen.called:
            first_args = mock_popen.call_args_list[0][0][0]
            assert nonexistent not in first_args


# ─────────────────────────────────────────────────────────────────
# open_url — cmd /c start fallback
# ─────────────────────────────────────────────────────────────────

class TestOpenUrlCmdStart:
    def test_no_chrome_uses_cmd_start(self):
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.subprocess.Popen") as mock_popen:
                result = open_url("https://example.com")

        assert result is True
        args = mock_popen.call_args[0][0]
        assert "cmd" in args
        assert "/c" in args
        assert "start" in args
        assert "https://example.com" in args

    def test_url_with_ampersand_passed_correctly(self):
        url = "https://www.korail.com/ticket/search?a=1&b=2"
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.subprocess.Popen") as mock_popen:
                open_url(url)

        args = mock_popen.call_args[0][0]
        assert url in args

    def test_cmd_oserror_falls_to_webbrowser(self):
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.subprocess.Popen", side_effect=OSError):
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
            with patch("src.utils.browser.subprocess.Popen", side_effect=OSError):
                with patch("src.utils.browser.webbrowser.open_new_tab") as mock_wb:
                    result = open_url("https://korail.com")

        assert result is True
        mock_wb.assert_called_once_with("https://korail.com")

    def test_all_methods_fail_returns_false(self):
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.subprocess.Popen", side_effect=OSError):
                with patch(
                    "src.utils.browser.webbrowser.open_new_tab",
                    side_effect=Exception("no browser"),
                ):
                    result = open_url("https://example.com")

        assert result is False

    def test_returns_true_on_success(self):
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.subprocess.Popen", side_effect=OSError):
                with patch("src.utils.browser.webbrowser.open_new_tab", return_value=None):
                    result = open_url("https://example.com")

        assert result is True

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
        """Chrome 파일이 없으면 Popen 호출 없이 ctypes ShellExecuteW로 넘어가야 함"""
        nonexistent = str(tmp_path / "nonexistent_chrome.exe")

        with patch("src.utils.browser._get_chrome_paths", return_value=(nonexistent,)):
            with patch("src.utils.browser.subprocess.Popen") as mock_popen:
                with patch("src.utils.browser.ctypes") as mock_ctypes:
                    mock_ctypes.windll.shell32.ShellExecuteW.return_value = 42
                    result = open_url("https://example.com")

        mock_popen.assert_not_called()
        assert result is True
        mock_ctypes.windll.shell32.ShellExecuteW.assert_called_once()


# ─────────────────────────────────────────────────────────────────
# open_url — ctypes ShellExecuteW (2순위, exe 환경 포함)
# ─────────────────────────────────────────────────────────────────

class TestOpenUrlCtypes:
    def test_no_chrome_uses_ctypes_shell_execute(self):
        """Chrome 없으면 ctypes ShellExecuteW 호출"""
        mock_shell32 = MagicMock()
        mock_shell32.ShellExecuteW.return_value = 42  # >32 = success

        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.ctypes") as mock_ctypes:
                mock_ctypes.windll.shell32.ShellExecuteW.return_value = 42
                result = open_url("https://example.com")

        assert result is True
        mock_ctypes.windll.shell32.ShellExecuteW.assert_called_once_with(
            None, "open", "https://example.com", None, None, 1
        )

    def test_shell_execute_fail_value_falls_to_startfile(self):
        """ShellExecuteW 반환값 ≤32이면 os.startfile로 fallback"""
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.ctypes") as mock_ctypes:
                mock_ctypes.windll.shell32.ShellExecuteW.return_value = 2  # ≤32 = fail
                with patch("src.utils.browser.os.startfile") as mock_sf:
                    result = open_url("https://example.com")

        assert result is True
        mock_sf.assert_called_once_with("https://example.com")

    def test_ctypes_exception_falls_to_startfile(self):
        """ctypes 예외 시 os.startfile로 fallback"""
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.ctypes", side_effect=Exception("no ctypes")):
                with patch("src.utils.browser.os.startfile") as mock_sf:
                    result = open_url("https://example.com")

        assert result is True
        mock_sf.assert_called_once_with("https://example.com")

    def test_url_with_ampersand_passed_intact(self):
        """& 포함 URL이 ShellExecuteW에 그대로 전달됨"""
        url = "https://korail.com?a=1&b=2&c=3"
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.ctypes") as mock_ctypes:
                mock_ctypes.windll.shell32.ShellExecuteW.return_value = 42
                open_url(url)

        call_args = mock_ctypes.windll.shell32.ShellExecuteW.call_args[0]
        assert call_args[2] == url  # 3번째 인자가 URL (변형 없음)


# ─────────────────────────────────────────────────────────────────
# open_url — os.startfile fallback (3순위)
# ─────────────────────────────────────────────────────────────────

class TestOpenUrlStartfile:
    def test_ctypes_fail_uses_startfile(self):
        """ctypes 실패하면 os.startfile 로 URL 열기"""
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.ctypes") as mock_ctypes:
                mock_ctypes.windll.shell32.ShellExecuteW.return_value = 2  # fail
                with patch("src.utils.browser.os.startfile") as mock_sf:
                    result = open_url("https://example.com")

        assert result is True
        mock_sf.assert_called_once_with("https://example.com")

    def test_startfile_oserror_falls_to_webbrowser(self):
        """ctypes + os.startfile 모두 실패 시 webbrowser fallback"""
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.ctypes") as mock_ctypes:
                mock_ctypes.windll.shell32.ShellExecuteW.return_value = 2  # fail
                with patch("src.utils.browser.os.startfile", side_effect=OSError):
                    with patch("src.utils.browser.webbrowser.open_new_tab") as mock_wb:
                        result = open_url("https://example.com")

        assert result is True
        mock_wb.assert_called_once_with("https://example.com")

    def test_startfile_attribute_error_falls_to_webbrowser(self):
        """비-Windows os.startfile 없을 때 webbrowser fallback"""
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.ctypes") as mock_ctypes:
                mock_ctypes.windll.shell32.ShellExecuteW.return_value = 2
                with patch("src.utils.browser.os.startfile", side_effect=AttributeError):
                    with patch("src.utils.browser.webbrowser.open_new_tab") as mock_wb:
                        result = open_url("https://example.com")

        assert result is True
        mock_wb.assert_called_once_with("https://example.com")


# ─────────────────────────────────────────────────────────────────
# open_url — webbrowser fallback (4순위)
# ─────────────────────────────────────────────────────────────────

class TestOpenUrlWebbrowser:
    def _no_chrome_ctypes_fail_startfile_fail(self):
        """Chrome 없음 + ctypes 실패 + startfile 실패 컨텍스트"""
        return (
            patch("src.utils.browser._get_chrome_paths", return_value=()),
            patch("src.utils.browser.ctypes") ,
            patch("src.utils.browser.os.startfile", side_effect=OSError),
        )

    def test_webbrowser_called_when_all_else_fails(self):
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.ctypes") as mock_ctypes:
                mock_ctypes.windll.shell32.ShellExecuteW.return_value = 2
                with patch("src.utils.browser.os.startfile", side_effect=OSError):
                    with patch("src.utils.browser.webbrowser.open_new_tab") as mock_wb:
                        result = open_url("https://korail.com")

        assert result is True
        mock_wb.assert_called_once_with("https://korail.com")

    def test_all_methods_fail_returns_false(self):
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.ctypes") as mock_ctypes:
                mock_ctypes.windll.shell32.ShellExecuteW.return_value = 2
                with patch("src.utils.browser.os.startfile", side_effect=OSError):
                    with patch(
                        "src.utils.browser.webbrowser.open_new_tab",
                        side_effect=Exception("no browser"),
                    ):
                        result = open_url("https://example.com")

        assert result is False

    def test_returns_true_on_success(self):
        with patch("src.utils.browser._get_chrome_paths", return_value=()):
            with patch("src.utils.browser.ctypes") as mock_ctypes:
                mock_ctypes.windll.shell32.ShellExecuteW.return_value = 2
                with patch("src.utils.browser.os.startfile", side_effect=OSError):
                    with patch("src.utils.browser.webbrowser.open_new_tab", return_value=None):
                        result = open_url("https://example.com")

        assert result is True

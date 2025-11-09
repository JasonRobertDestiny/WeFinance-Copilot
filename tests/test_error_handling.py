"""Tests for the error handling helpers."""

from __future__ import annotations

import time

import pytest

from utils.error_handling import (
    UserFacingError,
    _convert_to_user_facing_error,
    safe_call,
)


def test_safe_call_success():
    """Decorator should leave successful calls untouched."""

    @safe_call(timeout=5)
    def success_func():
        return "success"

    assert success_func() == "success"


def test_safe_call_with_fallback():
    """Fallback value should be returned when provided."""

    @safe_call(timeout=5, fallback="fallback", error_message="失败")
    def failing_func():
        raise ValueError("boom")

    assert failing_func() == "fallback"


def test_safe_call_without_fallback_raises_user_error():
    """When fallback is missing, convert to UserFacingError."""

    @safe_call(timeout=5, error_message="自定义错误")
    def failing_func():
        raise ValueError("bad input")

    with pytest.raises(UserFacingError) as exc_info:
        failing_func()

    assert "自定义错误" in exc_info.value.message


def test_safe_call_timeout_behaviour():
    """Timeout should raise on Unix but still allow Windows to proceed."""

    @safe_call(timeout=1, error_message="超时了")
    def slow_func():
        time.sleep(3)
        return "done"

    try:
        result = slow_func()
        assert result == "done"
    except UserFacingError as exc:
        assert "超时" in exc.message


def test_safe_call_preserves_user_facing_error():
    """Existing UserFacingError should not be double wrapped."""

    @safe_call(timeout=5)
    def user_error_func():
        raise UserFacingError("已存在的错误", suggestion="请重试")

    with pytest.raises(UserFacingError) as exc_info:
        user_error_func()

    assert exc_info.value.message == "已存在的错误"


def test_safe_call_timeout_can_be_disabled():
    """Explicitly disabling timeout should just run the function."""

    @safe_call(timeout=None)
    def fast_func():
        return "ok"

    assert fast_func() == "ok"


def test_convert_handles_rate_limit():
    """429 style errors become rate limit user messages."""
    err = Exception("429 Too Many Requests from API")
    user_error = _convert_to_user_facing_error(err, "默认消息")
    assert "次数超过限制" in user_error.message


def test_convert_handles_auth_error():
    """401/auth issues map to credential guidance."""
    err = Exception("401 Unauthorized: Invalid API key")
    user_error = _convert_to_user_facing_error(err, "默认消息")
    assert "API密钥" in user_error.message


def test_convert_handles_network_error():
    """Network level failures mention connectivity."""
    err = ConnectionError("Network unreachable")  # type: ignore[name-defined]
    user_error = _convert_to_user_facing_error(err, "默认消息")
    assert "网络连接" in user_error.message


def test_convert_handles_json_error():
    """JSON parsing failures should mention format issues."""
    class DummyJSONError(Exception):
        pass

    err = DummyJSONError("JSONDecodeError: Expecting value")
    user_error = _convert_to_user_facing_error(err, "默认消息")
    assert "数据格式解析失败" in user_error.message


def test_convert_handles_file_error():
    """File/permission issues should surface actionable hint."""
    err = PermissionError("Permission denied")
    user_error = _convert_to_user_facing_error(err, "默认消息")
    assert "文件操作失败" in user_error.message


def test_convert_falls_back_to_default_message():
    """Unrecognised errors should use default message."""
    err = RuntimeError("something odd")
    user_error = _convert_to_user_facing_error(err, "默认消息")
    assert user_error.message == "默认消息"

"""Shared error handling utilities with user-friendly messaging."""

from __future__ import annotations

import functools
import logging
import signal
from typing import Any, Callable, TypeVar
from typing import ParamSpec

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


class UserFacingError(Exception):
    """Exception type that is safe to display directly to end users."""

    def __init__(
        self,
        message: str,
        *,
        suggestion: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion
        self.original_error = original_error


def safe_call(
    timeout: int | None = 30,
    *,
    fallback: Any | None = None,
    error_message: str = "操作失败，请稍后重试",
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator adding timeout protection and user-friendly error conversion.

    Args:
        timeout: Timeout window in seconds. None disables timeout enforcement.
        fallback: Optional value to return when an error occurs.
        error_message: Default error message when conversion cannot classify.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            alarm_supported = False

            def timeout_handler(signum: int, frame: Any) -> None:  # pragma: no cover
                raise TimeoutError(
                    f"Function {func.__name__} timed out after {timeout}s"
                )

            if timeout is not None:
                try:
                    signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(timeout)
                    alarm_supported = True
                except (AttributeError, ValueError):
                    # Windows 或非主线程不支持 SIGALRM
                    logger.debug(
                        "Timeout not supported for %s on this platform/context",
                        func.__name__,
                    )

            try:
                return func(*args, **kwargs)
            except TimeoutError as exc:
                logger.error("Timeout in %s: %s", func.__name__, exc)
                raise UserFacingError(
                    "操作超时，网络响应时间过长",
                    suggestion="请检查网络连接后重试，或选择手动输入",
                    original_error=exc,
                ) from exc
            except UserFacingError:
                raise
            except Exception as exc:  # pylint: disable=broad-except
                user_error = _convert_to_user_facing_error(exc, error_message)
                logger.error(
                    "Error in %s: %s: %s",
                    func.__name__,
                    exc.__class__.__name__,
                    exc,
                    exc_info=True,
                )
                if fallback is not None:
                    logger.info(
                        "Returning fallback value for %s after failure",
                        func.__name__,
                    )
                    return fallback  # type: ignore[return-value]
                raise user_error from exc
            finally:
                if timeout is not None and alarm_supported:
                    try:
                        signal.alarm(0)
                    except (AttributeError, ValueError):
                        pass

        return wrapper

    return decorator


def _convert_to_user_facing_error(
    error: Exception,
    default_message: str,
) -> UserFacingError:
    """
    Map technical exceptions to user-friendly descriptions.
    """

    error_str = str(error)
    error_type = error.__class__.__name__

    if "429" in error_str or "Too Many Requests" in error_str:
        return UserFacingError(
            "API调用次数超过限制，请稍后重试",
            suggestion="如果您是高频用户，建议升级API套餐或联系技术支持",
            original_error=error,
        )

    if any(
        keyword in error_str
        for keyword in ("401", "Unauthorized", "Invalid API key", "authentication")
    ):
        return UserFacingError(
            "API密钥配置错误或已过期",
            suggestion="请检查.env文件中的OPENAI_API_KEY配置是否正确",
            original_error=error,
        )

    if any(
        keyword in error_str
        for keyword in ("Network", "Connection", "Timeout", "unreachable")
    ) or error_type in {"ConnectionError", "HTTPError", "Timeout", "RequestException"}:
        return UserFacingError(
            "网络连接不稳定，请检查网络设置",
            suggestion="确保网络畅通且能访问OpenAI API服务",
            original_error=error,
        )

    if "JSON" in error_str or error_type == "JSONDecodeError":
        return UserFacingError(
            "数据格式解析失败，API返回了非预期格式",
            suggestion="这可能是临时问题，请重试或联系技术支持",
            original_error=error,
        )

    if error_type in {"FileNotFoundError", "PermissionError", "IOError", "OSError"}:
        return UserFacingError(
            "文件操作失败，可能是权限或路径问题",
            suggestion="请检查文件路径是否正确，以及是否有读写权限",
            original_error=error,
        )

    return UserFacingError(
        default_message,
        suggestion="请刷新页面重试，如果问题持续请联系技术支持",
        original_error=error,
    )

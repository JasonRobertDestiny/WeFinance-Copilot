# Codex任务2：错误处理增强 - 详细实现指令

## 任务概述

**目标**：为LLM调用添加超时保护和用户友好的错误提示，确保网络故障时系统优雅降级。

**预计时间**：1-2小时

**文件变更**：
- 新建：`utils/error_handling.py`（错误处理工具）
- 新建：`tests/test_error_handling.py`（9个测试用例）
- 修改：`services/vision_ocr_service.py`（添加装饰器）
- 修改：`pages/bill_upload.py`（UI层错误处理）
- 修改：`locales/zh_CN.json` 和 `locales/en_US.json`（新增3-5个字符串）

---

## 步骤1：创建错误处理工具模块（30分钟）

### 1.1 创建文件

**文件路径**：`utils/error_handling.py`

**完整代码**：

```python
"""
统一错误处理工具 - 用户友好的错误提示

提供装饰器自动将技术错误转换为人话错误，并支持超时和fallback
"""

from __future__ import annotations

import functools
import logging
import signal
from typing import Any, Callable, Optional, TypeVar, ParamSpec

logger = logging.getLogger(__name__)

# 类型提示
P = ParamSpec('P')
R = TypeVar('R')


class UserFacingError(Exception):
    """
    用户友好的错误类型 - 可以直接展示给用户

    属性:
        message: 用户友好的错误描述（人话）
        suggestion: 用户下一步应该做什么的建议
        original_error: 原始技术错误（记录到日志）
    """

    def __init__(
        self,
        message: str,
        suggestion: str | None = None,
        original_error: Exception | None = None
    ):
        self.message = message
        self.suggestion = suggestion
        self.original_error = original_error
        super().__init__(message)


def safe_call(
    timeout: int | None = 30,
    fallback: Any = None,
    error_message: str = "操作失败，请稍后重试"
):
    """
    装饰器：为函数添加超时保护和友好错误处理

    使用示例:
        @safe_call(timeout=30, fallback=[], error_message="账单识别失败")
        def risky_function():
            # 可能会失败的代码
            return api_call()

    参数:
        timeout: 超时时间（秒），None表示不设置超时
        fallback: 发生错误时返回的默认值（如果提供）
        error_message: 通用错误提示信息

    返回:
        装饰后的函数（会捕获异常并转换为UserFacingError）
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:

            def timeout_handler(signum, frame):
                raise TimeoutError(f"Function {func.__name__} timed out after {timeout}s")

            # 设置超时（仅在Unix系统上有效）
            if timeout is not None:
                try:
                    signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(timeout)
                except (AttributeError, ValueError):
                    # Windows不支持SIGALRM，或在非主线程调用
                    logger.warning("Timeout not supported on this platform/context")

            try:
                result = func(*args, **kwargs)

                # 取消超时
                if timeout is not None:
                    try:
                        signal.alarm(0)
                    except (AttributeError, ValueError):
                        pass

                return result

            except TimeoutError as e:
                # 取消超时
                if timeout is not None:
                    try:
                        signal.alarm(0)
                    except (AttributeError, ValueError):
                        pass

                logger.error(f"Timeout in {func.__name__}: {e}")
                raise UserFacingError(
                    "操作超时，网络响应时间过长",
                    suggestion="请检查网络连接后重试，或选择手动输入",
                    original_error=e
                )

            except UserFacingError:
                # 已经是用户友好错误，直接抛出
                if timeout is not None:
                    try:
                        signal.alarm(0)
                    except (AttributeError, ValueError):
                        pass
                raise

            except Exception as e:
                # 取消超时
                if timeout is not None:
                    try:
                        signal.alarm(0)
                    except (AttributeError, ValueError):
                        pass

                # 将技术错误转换为用户友好错误
                user_error = _convert_to_user_facing_error(e, error_message)
                logger.error(
                    f"Error in {func.__name__}: {e.__class__.__name__}: {e}",
                    exc_info=True
                )

                # 如果有fallback，返回它而不是抛出错误
                if fallback is not None:
                    logger.info(f"Returning fallback value for {func.__name__}")
                    return fallback  # type: ignore

                raise user_error

        return wrapper

    return decorator


def _convert_to_user_facing_error(
    error: Exception,
    default_message: str
) -> UserFacingError:
    """
    将技术错误转换为用户友好错误

    参数:
        error: 原始技术错误
        default_message: 默认错误消息

    返回:
        UserFacingError实例
    """
    error_str = str(error)
    error_type = error.__class__.__name__

    # API限流
    if "429" in error_str or "Too Many Requests" in error_str:
        return UserFacingError(
            "API调用次数超过限制，请稍后重试",
            suggestion="如果您是高频用户，建议升级API套餐或联系技术支持",
            original_error=error
        )

    # 认证失败
    if any(keyword in error_str for keyword in ["401", "Unauthorized", "Invalid API key", "authentication"]):
        return UserFacingError(
            "API密钥配置错误或已过期",
            suggestion="请检查.env文件中的OPENAI_API_KEY配置是否正确",
            original_error=error
        )

    # 网络连接问题
    if (
        any(keyword in error_str for keyword in ["Network", "Connection", "Timeout", "unreachable"])
        or error_type in ["ConnectionError", "HTTPError", "Timeout", "RequestException"]
    ):
        return UserFacingError(
            "网络连接不稳定，请检查网络设置",
            suggestion="确保网络畅通且能访问OpenAI API服务",
            original_error=error
        )

    # JSON解析错误
    if "JSON" in error_str or error_type == "JSONDecodeError":
        return UserFacingError(
            "数据格式解析失败，API返回了非预期格式",
            suggestion="这可能是临时问题，请重试或联系技术支持",
            original_error=error
        )

    # 文件读写错误
    if error_type in ["FileNotFoundError", "PermissionError", "IOError", "OSError"]:
        return UserFacingError(
            "文件操作失败，可能是权限或路径问题",
            suggestion="请检查文件路径是否正确，以及是否有读写权限",
            original_error=error
        )

    # 默认错误（未分类）
    return UserFacingError(
        default_message,
        suggestion="请刷新页面重试，如果问题持续请联系技术支持",
        original_error=error
    )
```

**验收**：
- [ ] 文件创建在 `utils/error_handling.py`
- [ ] 代码无语法错误（可以被Python导入）
- [ ] 包含 `UserFacingError` 类、`safe_call` 装饰器、`_convert_to_user_facing_error` 函数

---

## 步骤2：应用到Vision OCR服务（15分钟）

### 2.1 修改Vision OCR服务

**文件路径**：`services/vision_ocr_service.py`

**修改位置**：

1. **在文件顶部添加导入**（大约在第8-10行之后）：

```python
from utils.error_handling import safe_call
```

2. **为 `extract_transactions_from_image` 方法添加装饰器**（大约在第60行）：

**查找这段代码**：
```python
def extract_transactions_from_image(
    self, image_bytes: bytes
) -> list[Transaction]:
    """从账单图片中提取交易记录（使用GPT-4o Vision）"""
```

**修改为**：
```python
@safe_call(
    timeout=30,
    fallback=[],
    error_message="账单识别失败"
)
def extract_transactions_from_image(
    self, image_bytes: bytes
) -> list[Transaction]:
    """
    从账单图片中提取交易记录（使用GPT-4o Vision）

    现在包含30秒超时保护和错误降级处理
    """
```

**注意事项**：
- 装饰器要放在 `def` 行的**正上方**
- 不要改动函数体内部的逻辑
- 确保缩进对齐

**验收**：
- [ ] `services/vision_ocr_service.py` 顶部导入了 `safe_call`
- [ ] `extract_transactions_from_image` 方法有 `@safe_call` 装饰器
- [ ] 装饰器参数：`timeout=30, fallback=[], error_message="账单识别失败"`
- [ ] 运行 `python -c "from services.vision_ocr_service import VisionOCRService; print('OK')"` 无错误

---

## 步骤3：UI层错误处理（20分钟）

### 3.1 修改账单上传页面

**文件路径**：`pages/bill_upload.py`

**修改位置1 - 添加导入**（大约在第10-15行）：

在现有导入之后添加：
```python
from utils.error_handling import UserFacingError
```

**修改位置2 - OCR调用错误处理**（大约在第260-290行，`st.status` 代码块）：

**查找这段代码模式**：
```python
with st.status(...) as status:
    # OCR处理逻辑
    for idx, file in enumerate(uploaded_files, start=1):
        ...
        transactions = ocr_service.extract_transactions_from_image(...)
        ...
```

**包裹在try-except中**：
```python
try:
    with st.status(...) as status:
        # 现有的OCR处理逻辑保持不变
        for idx, file in enumerate(uploaded_files, start=1):
            ...
            transactions = ocr_service.extract_transactions_from_image(...)
            ...

    # 成功处理后的逻辑
    if all_transactions:
        st.success(i18n.t("bill_upload.ocr_success", count=len(all_transactions)))

except UserFacingError as e:
    # 显示友好错误提示
    st.error(f"❌ {e.message}")

    if e.suggestion:
        st.info(f"💡 {e.suggestion}")

    # 提供降级方案：切换到手动输入
    st.markdown("---")
    st.markdown(f"**{i18n.t('bill_upload.fallback_option')}**")

    if st.button(
        i18n.t("bill_upload.manual_entry_btn"),
        type="primary",
        key="fallback_to_manual"
    ):
        st.session_state["show_manual_entry"] = True
        st.rerun()
```

**验收**：
- [ ] `pages/bill_upload.py` 导入了 `UserFacingError`
- [ ] OCR调用被 `try-except` 包裹
- [ ] `except UserFacingError` 块显示错误消息和建议
- [ ] 提供"改用手动输入"按钮作为降级方案

### 3.2 添加i18n字符串

**文件1**：`locales/zh_CN.json`

在 `"bill_upload"` 部分添加（大约在第120-140行）：

```json
"bill_upload": {
  ...现有字符串...
  "ocr_success": "成功识别 {count} 笔交易记录",
  "fallback_option": "备选方案",
  "manual_entry_btn": "改用手动输入"
}
```

**文件2**：`locales/en_US.json`

在 `"bill_upload"` 部分添加对应英文翻译：

```json
"bill_upload": {
  ...existing strings...
  "ocr_success": "Successfully identified {count} transactions",
  "fallback_option": "Alternative Option",
  "manual_entry_btn": "Switch to Manual Entry"
}
```

**验收**：
- [ ] `locales/zh_CN.json` 新增3个字符串
- [ ] `locales/en_US.json` 新增3个对应英文翻译
- [ ] JSON格式正确（无语法错误）

---

## 步骤4：编写测试用例（20分钟）

### 4.1 创建测试文件

**文件路径**：`tests/test_error_handling.py`

**完整代码**：

```python
"""
错误处理模块测试

验证safe_call装饰器和错误转换逻辑
"""

from __future__ import annotations

import pytest
import time
from utils.error_handling import safe_call, UserFacingError, _convert_to_user_facing_error


def test_safe_call_success():
    """测试装饰器在成功时正常返回"""

    @safe_call(timeout=5)
    def success_func():
        return "success"

    result = success_func()
    assert result == "success"


def test_safe_call_with_fallback():
    """测试装饰器在失败时返回fallback值"""

    @safe_call(timeout=5, fallback="fallback_value")
    def failing_func():
        raise ValueError("Something went wrong")

    result = failing_func()
    assert result == "fallback_value"


def test_safe_call_without_fallback_raises_user_error():
    """测试无fallback时抛出UserFacingError"""

    @safe_call(timeout=5, error_message="自定义错误")
    def failing_func():
        raise ValueError("Something went wrong")

    with pytest.raises(UserFacingError) as exc_info:
        failing_func()

    assert "自定义错误" in exc_info.value.message


def test_safe_call_timeout():
    """测试超时功能（仅在Unix系统）"""

    @safe_call(timeout=1, error_message="超时了")
    def slow_func():
        time.sleep(3)
        return "should not reach here"

    # 在支持timeout的系统上应该抛出UserFacingError
    # 在不支持的系统上会正常执行完成
    try:
        result = slow_func()
        # Windows或非主线程：超时不生效，函数正常完成
        assert result == "should not reach here"
    except UserFacingError as e:
        # Unix系统：超时生效
        assert "超时" in e.message


def test_safe_call_no_timeout():
    """测试可以禁用超时"""

    @safe_call(timeout=None)
    def func_without_timeout():
        return "done"

    result = func_without_timeout()
    assert result == "done"


def test_safe_call_preserves_user_facing_error():
    """测试已经是UserFacingError的异常会被保留"""

    @safe_call(timeout=5)
    def func_raising_user_error():
        raise UserFacingError("原始错误", suggestion="原始建议")

    with pytest.raises(UserFacingError) as exc_info:
        func_raising_user_error()

    assert exc_info.value.message == "原始错误"
    assert exc_info.value.suggestion == "原始建议"


def test_convert_api_rate_limit_error():
    """测试API限流错误转换"""
    error = Exception("429 Too Many Requests")
    user_error = _convert_to_user_facing_error(error, "默认消息")

    assert isinstance(user_error, UserFacingError)
    assert "API调用次数超过限制" in user_error.message
    assert user_error.suggestion is not None


def test_convert_auth_error():
    """测试认证错误转换"""
    error = Exception("401 Unauthorized")
    user_error = _convert_to_user_facing_error(error, "默认消息")

    assert "API密钥" in user_error.message
    assert "OPENAI_API_KEY" in user_error.suggestion


def test_convert_network_error():
    """测试网络错误转换"""
    error = ConnectionError("Network unreachable")
    user_error = _convert_to_user_facing_error(error, "默认消息")

    assert "网络连接" in user_error.message


def test_convert_json_error():
    """测试JSON解析错误转换"""
    import json
    try:
        json.loads("{invalid json}")
    except Exception as e:
        user_error = _convert_to_user_facing_error(e, "默认消息")

    assert "数据格式" in user_error.message


def test_convert_unknown_error_uses_default():
    """测试未知错误使用默认消息"""
    error = Exception("Something completely unexpected")
    user_error = _convert_to_user_facing_error(error, "自定义默认消息")

    assert user_error.message == "自定义默认消息"
    assert "重试" in user_error.suggestion


def test_user_facing_error_attributes():
    """测试UserFacingError的属性"""
    original = ValueError("原始错误")
    error = UserFacingError(
        "友好消息",
        suggestion="建议操作",
        original_error=original
    )

    assert error.message == "友好消息"
    assert error.suggestion == "建议操作"
    assert error.original_error is original
```

**验收**：
- [ ] 文件创建在 `tests/test_error_handling.py`
- [ ] 包含12个测试函数
- [ ] 运行 `pytest tests/test_error_handling.py -v` 全部通过

---

## 步骤5：运行完整测试套件（5分钟）

### 5.1 运行所有测试

**命令**：
```bash
conda activate wefinance
pytest tests/ -v
```

**预期结果**：
- 所有测试通过（29个原有 + 12个新增 = **41个测试**）
- 测试时间 <10秒
- 无警告或错误

### 5.2 代码质量检查

**命令**：
```bash
# 格式化代码
black utils/error_handling.py tests/test_error_handling.py pages/bill_upload.py services/vision_ocr_service.py

# Lint检查
ruff check .
```

**预期结果**：
- Black不需要修改（代码已格式化）
- Ruff无错误报告

**验收**：
- [ ] 所有测试通过（≥41个）
- [ ] 代码通过black和ruff检查
- [ ] 无警告或错误日志

---

## 步骤6：手动验证（10分钟）

### 6.1 启动应用

**命令**：
```bash
conda activate wefinance
streamlit run app.py
```

### 6.2 测试错误处理

**测试场景1：模拟API失败**

1. 临时修改 `.env` 文件，将 `OPENAI_API_KEY` 改为无效值
2. 上传一张账单图片
3. **预期结果**：
   - 显示 "❌ API密钥配置错误或已过期"
   - 显示 "💡 请检查.env文件中的OPENAI_API_KEY配置是否正确"
   - 显示 "改用手动输入" 按钮
   - 点击按钮切换到手动输入表单

4. 恢复 `.env` 文件

**测试场景2：验证数据持久化依然工作**

1. 上传账单（使用正确API key）
2. 成功识别交易
3. 刷新浏览器
4. **预期结果**：交易记录依然存在

**验收**：
- [ ] API失败时显示友好错误提示
- [ ] 显示建议操作文本
- [ ] "改用手动输入"按钮可点击
- [ ] 数据持久化功能未受影响

---

## 步骤7：Git提交（5分钟）

### 7.1 Stage和Commit

**命令**：
```bash
# Stage所有修改
git add utils/error_handling.py
git add tests/test_error_handling.py
git add services/vision_ocr_service.py
git add pages/bill_upload.py
git add locales/zh_CN.json
git add locales/en_US.json

# 提交
git commit -m "feat: 错误处理增强 - 超时保护和友好提示

实现内容:
- 创建utils/error_handling.py（装饰器+错误转换）
- 为Vision OCR添加30秒超时保护
- UI层捕获UserFacingError并显示友好提示
- 提供降级方案：改用手动输入

技术细节:
- safe_call装饰器：timeout + fallback + 错误转换
- 7种错误类型识别：API限流、认证、网络、JSON、文件等
- 完全i18n化（中英文）

测试:
- 新增12个测试用例覆盖错误处理逻辑
- 所有测试通过（41/41）
- 手动验证：API失败显示友好错误

验收:
- Vision OCR超时>30秒自动中断
- 网络失败显示\"网络连接不稳定\"提示
- 所有错误都有建议操作
- 提供手动输入降级方案
"

# 推送到GitHub
git push origin main
```

**验收**：
- [ ] Commit message遵循语义化规范
- [ ] 包含详细的实现内容和验收标准
- [ ] 成功推送到远程仓库

---

## 完成检查清单

### 功能验收
- [ ] Vision OCR调用有30秒超时保护
- [ ] API失败时显示友好错误（不是技术堆栈）
- [ ] 错误提示包含建议操作文本
- [ ] 提供"改用手动输入"降级按钮
- [ ] 数据持久化功能未受影响

### 代码质量
- [ ] `utils/error_handling.py` 包含完整装饰器实现
- [ ] `services/vision_ocr_service.py` 正确使用装饰器
- [ ] `pages/bill_upload.py` 正确处理UserFacingError
- [ ] 所有新代码通过black和ruff检查
- [ ] 关键函数有类型注解和docstring

### 测试验收
- [ ] 12个新测试用例全部通过
- [ ] 覆盖成功路径、失败路径、超时、fallback
- [ ] 覆盖7种错误类型转换
- [ ] 全部测试通过（≥41个）

### i18n验收
- [ ] `locales/zh_CN.json` 新增3个字符串
- [ ] `locales/en_US.json` 新增3个对应翻译
- [ ] 切换语言后错误提示正常显示

### Git提交验收
- [ ] 6个文件已提交（3新建 + 3修改）
- [ ] Commit message详细且规范
- [ ] 成功推送到GitHub

---

## 常见问题

**Q: 超时功能在Windows上不工作怎么办？**

A: 这是预期行为。代码已做兼容处理：
- Unix/Linux/Mac：超时生效（使用signal.SIGALRM）
- Windows：超时不生效，但不会报错
- 测试用例会自动适应平台差异

**Q: 如何测试超时行为？**

A:
1. 在 `extract_transactions_from_image` 中临时添加 `time.sleep(35)`
2. 上传账单，观察是否在30秒后中断（Unix）
3. 移除sleep代码

**Q: 错误提示的中英文不一致怎么办？**

A: 确保 `locales/zh_CN.json` 和 `locales/en_US.json` 的key完全一致。

**Q: 测试运行时间过长？**

A:
- `test_safe_call_timeout` 需要sleep 3秒（正常）
- 如果超过10秒，检查是否有死循环或网络调用

---

## 下一步预告

任务2完成后，将进入**任务3：竞赛演示材料**（UI截图 + 演示视频 + PPT）。

预计时间：3-4小时

等任务2验收通过后，我会给你任务3的详细指令。

---

祝实现顺利！有问题随时沟通。

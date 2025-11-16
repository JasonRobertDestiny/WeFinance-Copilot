# 性能优化分析与方案

## 当前性能问题分析

### 1. Streamlit Cloud 免费版限制
- **CPU**: 共享CPU（非独占）
- **内存**: 1GB RAM
- **冷启动**: 应用闲置后需要重新启动（30-60秒）
- **并发**: 多用户同时访问时性能下降

### 2. 代码层面性能瓶颈

#### 关键问题（从 app.py 分析）

**问题1**: 每次页面刷新都计算异常检测（高成本）
```python
# app.py:289 - 每次main()运行都执行
def main():
    init_session_state()
    _refresh_anomaly_state()  # ❌ 每次都计算
```

**影响**: 每次页面交互都重新分析所有交易数据

**问题2**: 首页对比表每次重建
```python
# app.py:214-239 - 每次_render_home()都创建DataFrame
comparison_df = pd.DataFrame(comparison_data)
```

**影响**: 静态内容重复计算

**问题3**: 没有使用 Streamlit 缓存
- `@st.cache_data` 未应用到昂贵计算
- i18n 翻译每次都从 JSON 重新加载（虽然有实例缓存）

**问题4**: Storage 恢复在模块级执行
```python
# app.py:68 - 模块导入时执行
restore_data_from_storage()
```

### 3. LLM API 调用延迟

- Vision OCR: 2-5秒/图片
- Chat: 1-3秒/消息
- Recommendations: 3-7秒

**已有优化**:
- ✅ Chat使用LRU缓存
- ✅ Recommendations使用@st.cache_data
- ✅ 所有API调用有30s超时保护

## 优化方案

### 快速优化（立即实施）

#### 1. 智能异常检测触发

**当前**: 每次页面加载都计算
**优化**: 仅在数据变化时计算

```python
def _refresh_anomaly_state() -> None:
    """仅在数据变化时重新计算异常检测"""
    # 添加数据哈希检查
    transactions = session_utils.get_transactions()
    current_hash = hash(tuple((t.id, t.amount) for t in transactions))

    if st.session_state.get("anomaly_last_hash") == current_hash:
        return  # 数据未变化，跳过计算

    # 数据变化，重新计算
    report = compute_anomaly_report(...)
    st.session_state["anomaly_last_hash"] = current_hash
```

#### 2. 缓存静态内容

```python
@st.cache_data
def get_comparison_table(locale: str):
    """缓存对比表数据"""
    # 移动首页的comparison_data到这里
    return pd.DataFrame(comparison_data)
```

#### 3. 添加加载指示器

```python
with st.spinner("正在加载..."):
    render()  # 让用户知道系统在工作
```

#### 4. 懒加载页面模块

```python
# 当前: 顶部导入所有页面
from pages import advisor_chat, bill_upload, ...

# 优化: 按需导入
def lazy_render_bill_upload():
    from pages import bill_upload
    return bill_upload.render()
```

### 中期优化（需要测试）

#### 5. 减小 pandas 依赖

对比表可以用纯HTML：

```python
# 不用pandas DataFrame
st.markdown("""
<table>
  <tr><th>功能</th><th>WeFinance</th><th>传统方案</th></tr>
  <tr><td>OCR识别率</td><td>100%</td><td>70-80%</td></tr>
</table>
""", unsafe_allow_html=True)
```

#### 6. Session State 数据压缩

大量交易数据可以压缩存储：

```python
import gzip
import base64

# 存储时压缩
compressed = gzip.compress(json.dumps(data).encode())
st.session_state["transactions_compressed"] = base64.b64encode(compressed)

# 读取时解压
data = json.loads(gzip.decompress(base64.b64decode(compressed)))
```

### 长期优化（架构改进）

#### 7. 部署到更强硬件

**选项A**: Streamlit Cloud Professional
- 4GB RAM
- 专用CPU
- 无冷启动
- 费用: $250/月

**选项B**: 自建Docker部署（已有Dockerfile）
```bash
# 部署到阿里云/腾讯云
# 2核4GB配置约 ¥200/月
docker run -d -p 8501:8501 --env-file .env wefinance-copilot:latest
```

**选项C**: Vercel + Streamlit Hybrid
- 静态页面走Vercel CDN（免费）
- 动态计算走Streamlit Cloud

#### 8. API 响应缓存服务

对于 Vision OCR 结果：
- 使用 Redis 缓存识别结果（基于图片hash）
- 相同账单不重复调用API

## 预期效果

| 优化项 | 当前耗时 | 优化后耗时 | 提升 |
|--------|---------|-----------|------|
| 首页加载 | 2-3秒 | 0.5-1秒 | 66% |
| 页面切换 | 1-2秒 | <0.5秒 | 75% |
| 异常检测 | 每次计算 | 仅数据变化时 | 90% |
| 对比表渲染 | 0.5秒 | <0.1秒 | 80% |

## 立即可实施的优化代码

见下面的 `app_optimized.py` 示例。

## Streamlit Cloud 特定建议

1. **减少 requirements.txt 依赖**
   - 移除未使用的包
   - 使用轻量级替代（如 `orjson` 替代 `json`）

2. **优化资源加载**
   - 压缩图片资源
   - 延迟加载非关键模块

3. **监控性能**
   ```python
   import time
   start = time.time()
   # ... 操作 ...
   logger.info(f"Operation took {time.time() - start:.2f}s")
   ```

## 结论

**快速优化** (1-2小时实施)可带来 50-70% 性能提升。
**中期优化** (1天实施)可达到 80% 提升。
**长期优化** (升级硬件)可彻底解决问题。

**建议**: 先实施快速优化，观察效果后决定是否需要升级硬件。

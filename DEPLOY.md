# WeFinance 部署指南

## 1. 方案概览
- **快速演示 / 分享**：优先使用 Streamlit Community Cloud，零运维、一键从 GitHub 发布。
- **准生产 / 私有环境**：将同一代码包装为 Docker，部署到 ACK/TKE/EKS 等托管 K8s 或公司 GPU 服务器。
- **混合形态**：保留 Cloud 作为 Demo，同步一个自托管实例供真实账单流量，二者共用 `main` 分支代码。

## 2. Streamlit Community Cloud（推荐）
### 2.1 仓库准备
1. 根目录包含 `app.py`、`requirements.txt`，以及 `.streamlit/config.toml`（端口/主题）与 `.streamlit/secrets.toml.example`（供拷贝到 Cloud Secrets）。
2. 若需要系统依赖，可创建 `packages.txt`（例：`libgl1`、`libglib2.0-0`）。多数场景可仅依赖 `pip` 包。
3. 在本地执行 `streamlit run app.py` 确认 UI、OCR、LLM 调用均可用，再推送到 GitHub。

### 2.2 部署步骤
1. 登录 https://share.streamlit.io/ ，选择 **New app → From existing repo**，绑定 `WeFinance` 仓库与目标分支（通常 `main`）。
2. 在 **Advanced settings → Secrets** 粘贴 `.streamlit/secrets.toml.example` 的键，填写真实值：
   - `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `LLM_PROVIDER`
   - 可选：`TZ=Asia/Shanghai`、`WEFINANCE_STORAGE_FILE`（如需自定义缓存路径）。
3. 点击 **Deploy**。初次构建约 2–3 分钟，之后每次推送自动重新部署。若需强制刷新，可在 App Dashboard 里选择 **Rerun**。

### 2.3 运行验证
- 访问自动生成的 `https://<username>-wefinance.streamlit.app`。
- 上传 `assets/sample_bills/bill_dining.png` 验证 OCR；打开 “Insights / Advisor” 分页验证 LangChain 对话。
- 若日志显示权限错误，可在 Settings → Logs 中排查，并检查 Secrets 是否正确加载。

## 3. Secret 与配置管理
- 不要将 `.env` 或真实密钥加入仓库；仅提交 `.streamlit/secrets.toml.example` 作为模板。
- 在本地调试时，复制 `.env.example` → `.env` 并运行 `streamlit run app.py`；Cloud 端通过 Secrets 注入同名变量。
- 需要新增第三方服务时，先在 README/DEPLOY 更新变量说明，再在 Streamlit Secrets 中添加，保持文档与部署同步。

## 4. 后续扩展部署建议
1. **私有云容器**：使用 `python:3.10-slim` 作为基础镜像，拷贝代码与 `requirements.txt`，执行 `pip install -r requirements.txt`，然后以 `streamlit run app.py --server.port=8080 --server.headless=true` 作为入口；结合 K8s HPA 根据会话量扩缩容。
2. **内网 GPU 节点**：在公司机房配置 8 核 CPU + 32GB RAM + T4/RTX 3060，安装 Conda 环境 `conda env create -f environment.yml`，通过 Nginx 反向代理给内网用户，保障账单数据不出域。
3. **混合模式**：Streamlit Cloud 负责 Demo，私有云实例承载真实流量。通过 GitHub Actions 同步镜像或包，确保两端在 `main` 成功 CI 后再发版。

通过以上流程，既能快速部署演示环境，也为后续商业化部署预留了清晰路径。

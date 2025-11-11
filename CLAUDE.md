# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WeFinance Copilot is an AI-powered financial assistant for the 2025 Shenzhen Fintech Competition. It uses Vision LLM (GPT-4o) for bill OCR, conversational AI for financial advice, and explainable AI for investment recommendations.

**Key Architecture Decision**: Originally used PaddleOCR, but migrated to GPT-4o Vision OCR for 100% recognition accuracy (vs 0% with synthetic images). This is the core competitive advantage.

**Project Status**: Feature-complete for competition submission (deadline: 2025-11-16). Demo materials prepared (screenshots/, demo/wefinance_presentation.pptx).

## Essential Commands

### Environment Setup
```bash
# Activate conda environment (REQUIRED before any command)
conda activate wefinance

# First-time setup
conda env create -f environment.yml  # Create environment
pip install -r requirements.txt      # Development tools (pytest-cov, etc.)

# Update environment after modifying environment.yml
conda env update -f environment.yml --prune
```

**CRITICAL**: Always activate `conda activate wefinance` before running any command. System Python won't have required packages.

### Running the Application
```bash
# Standard mode (opens browser automatically)
streamlit run app.py --server.port 8501

# Background/headless mode
streamlit run app.py --server.port 8501 --server.headless true
```

Application opens at: `http://localhost:8501`

### Testing
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_ocr_service.py -v

# Run single test function
pytest tests/test_ocr_service.py::test_vision_ocr_integration -v

# Run with coverage report
pytest --cov=modules --cov=services --cov=utils --cov-report=term-missing

# Generate HTML coverage report (opens htmlcov/index.html in browser)
pytest --cov=modules --cov=services --cov=utils --cov-report=html
```

### Code Quality
```bash
# Format code (REQUIRED before commits)
black .

# Lint code
ruff check .
ruff check --fix .  # Auto-fix safe issues
```

### Vision OCR Testing
```bash
# Test Vision OCR with sample bills (uses assets/sample_bills/*.png)
python test_vision_ocr.py

# Expected: 100% recognition rate on all 3 sample bills
```

## Architecture Overview

### Core Innovation: Vision LLM Pipeline

**CRITICAL**: The OCR system underwent a major architectural shift:

```
Old (PaddleOCR): Image → PaddleOCR → Text → GPT-4o → Structured Data
New (Vision LLM): Image → GPT-4o Vision → Structured Data (ONE STEP)
```

**Why this matters**:
- PaddleOCR: 0% recognition on synthetic images, heavy dependencies (200MB models)
- Vision LLM: 100% recognition, zero additional dependencies, 2-5s per image
- **Implementation**: `services/vision_ocr_service.py` (161 lines)
- **Facade**: `services/ocr_service.py` maintains backward compatibility

### Data Flow Architecture

```
User Upload (pages/bill_upload.py)
    ↓
OCRService.process_files()
    ↓ (delegates to)
VisionOCRService.extract_transactions_from_image()
    ├─ Base64 encode image
    ├─ GPT-4o Vision API call (temp=0.0, structured prompt)
    ├─ JSON parsing → Transaction objects
    └─ Return List[Transaction]
    ↓
Session State (utils/session.py)
    ├─ st.session_state["transactions"]
    └─ Shared across all pages
    ↓
Multiple Consumers:
    ├─ Advisor Chat (modules/chat_manager.py)
    ├─ Investment Recommendations (services/recommendation_service.py)
    ├─ Spending Insights (modules/analysis.py)
    └─ Anomaly Detection (modules/analysis.py::compute_anomaly_report)
```

### Session State Management

**CRITICAL PATTERN**: Streamlit `session_state` is the single source of truth. All data flows through `utils/session.py` helper functions.

```python
# CORRECT: Centralized state management
from utils.session import set_transactions, get_transactions

set_transactions(transactions)  # In bill_upload.py
transactions = get_transactions()  # In other pages

# WRONG: Direct session_state manipulation
st.session_state["transactions"] = transactions  # Bypasses validation/serialization
```

**Why use helpers**:
- Ensures consistent serialization (Transaction → dict)
- Handles type normalization (dict → Transaction)
- Provides single point of truth for state keys

**Key session state keys**:
- `transactions`: List[dict] - Serialized Transaction objects (core data)
- `chat_history`: List[dict] - Conversation messages
- `locale`: str - "zh_CN" or "en_US" (triggers full UI refresh on change)
- `monthly_budget`: float - User's budget (default: 5000.0)
- `anomaly_flags`: List[dict] - Active anomaly alerts
- `anomaly_history`: List[dict] - Resolved anomalies with user feedback
- `trusted_merchants`: List[str] - Whitelist for anomaly detection
- `i18n`: I18n - Lazy-loaded translation instance

### Error Handling System (NEW - 2025-11-09)

**Architecture**: Unified error handling with user-friendly messaging.

**Location**: `utils/error_handling.py`

**Key Components**:

1. **UserFacingError**: Exception type safe to display to end users
   - Contains user-friendly message
   - Optional suggestion for resolution
   - Preserves original technical error for logging

2. **@safe_call decorator**: Adds timeout protection and error conversion
   ```python
   from utils.error_handling import safe_call

   @safe_call(timeout=30, fallback=[], error_message="OCR识别失败")
   def process_image(image_bytes):
       # API call that might timeout or fail
       return llm_api_call(image_bytes)
   ```

3. **Automatic error mapping**:
   - Network errors → "网络连接不稳定"
   - API auth errors → "API密钥配置错误"
   - Rate limits → "API调用次数超过限制"
   - JSON parse errors → "数据格式解析失败"

**Best practices**:
- Use `@safe_call` for all LLM API calls
- Set appropriate timeout (30s for vision, 15s for chat)
- Provide fallback values when graceful degradation is possible
- Custom error messages for domain-specific failures

### Persistent Storage System (NEW - 2025-11-09)

**Architecture**: File-based persistence for session data across browser refreshes.

**Location**: `utils/storage.py`

**Key Features**:
- JSON file backend (`~/.wefinance/data.json` by default)
- Automatic fallback to workspace if home directory is not writable
- Namespaced keys (`wefinance_` prefix)
- Thread-safe atomic writes

**Usage**:
```python
from utils.storage import save_to_storage, load_from_storage

# Save user preferences
save_to_storage("monthly_budget", 5000.0)

# Load with default fallback
budget = load_from_storage("monthly_budget", default=3000.0)
```

**Configuration**:
- Override storage path via `WEFINANCE_STORAGE_FILE` env variable
- Default paths (tried in order):
  1. `~/.wefinance/data.json` (preferred)
  2. `<workspace>/.wefinance/data.json` (fallback)

**When to use**:
- User preferences (budget, risk profile)
- Trusted merchant whitelist
- Anomaly detection history
- NOT for sensitive data (no encryption)

### LLM Integration Patterns

**Three LLM use cases**:

1. **Vision OCR** (`services/vision_ocr_service.py:60-160`):
   - Model: GPT-4o Vision
   - Input: Image bytes (base64 encoded)
   - Output: Structured JSON → List[Transaction]
   - Temperature: 0.0 (deterministic)
   - Timeout: 30s (via @safe_call decorator)
   - Prompt engineering: Specifies exact JSON format, valid categories, date format
   - Error handling: Returns empty list on failure (graceful degradation)

2. **Chat** (`modules/chat_manager.py`):
   - Model: GPT-4o (text)
   - Input: User query + transaction context + budget context
   - Output: Natural language financial advice
   - Timeout: 15s (via @safe_call decorator)
   - Caching: Query-level LRU cache (20 items, exact string match)
   - Context assembly: `_assemble_context()` formats transactions for prompt

3. **Recommendations** (`services/recommendation_service.py`):
   - Model: GPT-4o (text)
   - Input: Transactions + risk profile + investment goal
   - Output: Structured recommendation with reasoning chain (explainable AI)
   - Timeout: 30s (via @safe_call decorator)
   - Caching: Streamlit `@st.cache_data` on deterministic inputs (transaction hash)

### Internationalization (i18n)

**Architecture**: Lazy-loaded translation system with fallback mechanism.

```python
# CORRECT: Get translations
from utils.session import get_i18n

i18n = get_i18n()
title = i18n.t("chat.title")  # Returns "智能财务顾问" or "AI Financial Advisor"

# Translation file structure
locales/zh_CN.json  # Chinese translations
locales/en_US.json  # English translations
utils/i18n.py       # Core I18n class (lazy-loads JSON, caches translations)
```

**Fallback chain**: `i18n.t(key)` → locale file → fallback locale → key itself (if missing)

**Locale switching**:
```python
from utils.session import switch_locale
switch_locale("en_US")  # Updates session_state["locale"] + reloads I18n instance
# Triggers st.rerun() in app.py to refresh entire UI
```

**Implementation details**:
- JSON files: Nested dicts for namespacing (e.g., `"chat.title"`, `"app.welcome"`)
- Lazy loading: Files loaded on first `i18n.t()` call, cached in instance
- Session persistence: `st.session_state["i18n"]` persists I18n instance across reruns
- Cache invalidation: New I18n instance created on locale switch

## Critical Implementation Details

### Vision OCR Prompt Engineering

**Location**: `services/vision_ocr_service.py:77-96`

The prompt is carefully engineered for structured output:
- Specifies exact JSON format (no markdown code blocks)
- Lists valid categories: 餐饮、交通、购物、娱乐、医疗、教育、其他
- Requires YYYY-MM-DD date format
- Explicitly requests no markdown code blocks (but code handles them anyway)
- Returns empty array `[]` if no transactions found

**DO NOT** modify this prompt without testing against all sample bills in `assets/sample_bills/`.

**JSON parsing cleanup** (`vision_ocr_service.py:123-131`):
- Strips markdown code blocks: ````json` and `\`\`\``
- Handles malformed LLM responses gracefully
- Falls back to empty list on JSON parse failure

### Error Handling Philosophy

**Pattern**: Graceful degradation, not crash-and-burn.

```python
# Vision OCR failure → Return empty list, allow manual input
from utils.error_handling import safe_call

@safe_call(timeout=30, fallback=[], error_message="OCR识别失败")
def extract_transactions(image):
    # API call
    return results
```

**Why**: User experience > perfect execution. Always provide a fallback path.

**User-facing error messages**:
- Translated via i18n system: `i18n.t("errors.api_key_missing")`
- Converted via `error_handling.py` for technical errors
- Logged at appropriate levels: `logger.error()`, `logger.warning()`, `logger.info()`
- Never expose API keys, stack traces, or internal details to users

## Configuration

### Required .env Variables
```bash
# OpenAI-compatible API (REQUIRED)
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_BASE_URL=https://newapi.deepwisdom.ai/v1
OPENAI_MODEL=gpt-4o

# Optional: LLM provider selection (currently only supports openai)
LLM_PROVIDER=openai

# Optional: Storage path override
WEFINANCE_STORAGE_FILE=/custom/path/to/data.json
```

**Template file**: `.env.example` (copy to `.env` and fill in your API key)

**Security**:
- `.env` is git-ignored
- Never commit API keys to version control
- Loaded via `python-dotenv` in all services

### Conda Environment

**Python Version**: 3.10.x (specified in `environment.yml`)

**Why Conda**:
- Isolates scientific computing dependencies (numpy, pandas, scipy, opencv)
- Consistent environment across development machines

**Key Dependencies** (from requirements.txt):
- **Web Framework**: streamlit>=1.37,<2.0
- **LLM**: openai>=1.45.0, langchain>=0.2.10, langchain-openai>=0.1.7
- **Data**: pandas>=2.0, numpy>=1.26, scikit-learn>=1.4
- **Visualization**: plotly>=5.18
- **Models**: pydantic>=2.0
- **Utils**: python-dotenv>=1.0, pillow>=10.0

**IMPORTANT**: Always activate environment before running any command:
```bash
conda activate wefinance
```

**Updating dependencies**:
1. Modify `environment.yml` or `requirements.txt`
2. Run `conda env update -f environment.yml --prune`
3. Test all functionality
4. Commit changes

## Common Pitfalls

### 1. Forgetting to Activate Conda Environment
```bash
# WRONG: Uses system Python, missing packages
python test_vision_ocr.py

# CORRECT: Activates environment first
conda activate wefinance
python test_vision_ocr.py
```

**Symptoms**: `ModuleNotFoundError: No module named 'streamlit'`

### 2. Breaking Session State Consistency
```python
# WRONG: Direct manipulation bypasses validation
st.session_state["transactions"] = new_data

# CORRECT: Use helper functions from utils/session.py
from utils.session import set_transactions
set_transactions(new_data)
```

**Why helpers matter**: Ensures Transaction → dict serialization, type safety, validation.

### 3. Ignoring Vision OCR JSON Parsing

The Vision LLM sometimes wraps JSON in markdown code blocks:
```
```json
[{"date": "2025-11-01", ...}]
```
```

The code in `vision_ocr_service.py:123-131` handles this automatically. Don't bypass it.

### 4. Testing Without Sample Data

Use `assets/sample_bills/` for testing, not random images. These bills are:
- **bill_dining.png**: 4 dining transactions
- **bill_mixed.png**: 4 mixed-category transactions
- **bill_shopping.png**: 3 shopping transactions

Generated with `generate_sample_bills.py` using Noto CJK fonts for realistic Chinese text rendering.

### 5. Modifying Transaction Model Without Migration

`models/entities.py::Transaction` is used everywhere. Adding/removing fields requires:
1. Update model with default values for backward compatibility
2. Update all consumers (chat, analysis, recommendations, anomaly detection)
3. Update tests (integration tests will break)
4. Run full test suite: `pytest tests/ -v`

**Transaction model fields** (as of 2025-11-06):
- `id`: str
- `date`: str (YYYY-MM-DD format)
- `merchant`: str
- `category`: str (餐饮、交通、购物、娱乐、医疗、教育、其他)
- `amount`: float

### 6. Not Using Error Handling Utilities

**WRONG**: Raw API calls without protection
```python
def chat(query):
    response = openai.chat.completions.create(...)  # No timeout, no error handling
    return response.choices[0].message.content
```

**CORRECT**: Use @safe_call decorator
```python
from utils.error_handling import safe_call

@safe_call(timeout=15, fallback="抱歉，暂时无法回答")
def chat(query):
    response = openai.chat.completions.create(...)
    return response.choices[0].message.content
```

## Architecture Decisions Log

### 2025-11-09: Error Handling & Storage Systems

**Problem**: No unified error handling, no persistent storage across sessions.

**Solution**:
- Added `utils/error_handling.py` with @safe_call decorator and UserFacingError
- Added `utils/storage.py` for file-based persistence

**Impact**:
- Better UX: User-friendly error messages instead of technical stack traces
- Timeout protection: All LLM calls now have 15-30s timeouts
- Data persistence: User preferences survive browser refreshes
- Code simplification: Consistent error handling pattern across codebase

**Files Changed**:
- NEW: `utils/error_handling.py` (166 lines)
- NEW: `utils/storage.py` (147 lines)
- NEW: `tests/test_error_handling.py`
- NEW: `tests/test_storage.py`

### 2025-11-06: PaddleOCR → GPT-4o Vision

**Problem**: PaddleOCR couldn't recognize synthetic bill images (0% accuracy on `generate_sample_bills.py` output).

**Solution**: Replaced with GPT-4o Vision, achieving 100% accuracy.

**Impact**:
- **Completely removed** PaddlePaddle/PaddleOCR dependencies (2025-11-11)
- Simplified pipeline from 2-step to 1-step
- Increased API cost (~$0.01/image) but acceptable for MVP/competition
- Improved accuracy from 0% to 100% on synthetic images

**Files Changed**:
- NEW: `services/vision_ocr_service.py` (161 lines)
- MODIFIED: `services/ocr_service.py` (now delegates to VisionOCRService)
- REMOVED: PaddleOCR dependencies from `environment.yml`, `requirements.txt`, `.env.example`

**Migration path**: All code uses `OCRService` facade, which internally delegates to `VisionOCRService`.

## Demo Materials (NEW - 2025-11-09)

**Location**: `screenshots/` and `demo/`

### Screenshots for Competition Submission

**Chinese UI** (screenshots/):
- `01_homepage_progress_zh.png`: Homepage with feature overview
- `02_bill_upload_ocr_zh.png`: Bill upload and OCR results
- `03_spending_insights_zh.png`: Spending analysis dashboard
- `04_advisor_chat_zh.png`: AI financial advisor conversation
- `05_investment_recs_zh.png`: Investment recommendations with XAI
- `06_sidebar_zh.png`: Navigation sidebar

**English UI** (screenshots/):
- `07_homepage_progress_en.png`: English homepage
- `08_advisor_chat_en.png`: English chat interface

**Usage**: Include in competition presentation and documentation.

### Presentation Materials (demo/)

**Files**:
- `wefinance_presentation.pptx`: Competition presentation slides
- `video_script.md`: Video demonstration script
- `ppt_outline.md`: Presentation structure outline
- `checklist.md`: Pre-submission checklist

**Note**: PowerPoint generation scripts (`create_ppt_*.js`) use Node.js and officegen package.

## Debugging Tips

### Vision OCR Not Working

1. Check `.env` has valid `OPENAI_API_KEY`
2. Test API connectivity: `python test_vision_ocr.py`
3. Check logs: `services/vision_ocr_service.py` logs at INFO level
4. Verify image format: PNG/JPG/JPEG only (PDF not supported by Vision API)
5. Check API rate limits: `https://newapi.deepwisdom.ai/v1` may have limits

**Common errors**:
- `ValueError: OPENAI_API_KEY environment variable not set`: Missing/invalid `.env` file
- `UserFacingError: API密钥配置错误`: Invalid API key or authentication failure
- `UserFacingError: 操作超时`: Network timeout (check internet connection)
- Empty transaction list: Image might not contain recognizable bill data

### Streamlit Session State Issues

1. Check `utils/session.py` for state initialization: `init_session_state()` called in `app.py`
2. Use `st.session_state` debugger: Add `st.write(st.session_state)` temporarily
3. Verify state keys match between pages: Use constants from `utils/session.py::DEFAULT_STATE`
4. Check session persistence: Session state resets on browser refresh (expected behavior)
5. Use `utils/storage.py` for data that should persist across sessions

**Common issues**:
- `KeyError: 'transactions'`: `init_session_state()` not called before access
- Data not persisting: Check if using helper functions, not direct dict access
- Locale not switching: Missing `st.rerun()` after `switch_locale()`

### LLM Timeout/Failure

1. Check API rate limits: `https://newapi.deepwisdom.ai/v1` dashboard
2. Verify network connectivity to OpenAI-compatible endpoint
3. Review error logs: UserFacingError provides user-friendly context
4. Check API key validity: Test with `curl` or `python test_vision_ocr.py`

**Graceful degradation**:
- Vision OCR: Returns empty list via @safe_call(fallback=[])
- Chat: Returns error message via @safe_call(fallback="抱歉...")
- Recommendations: Returns empty list, shows UserFacingError message

### Storage Issues

1. Check storage file location: `~/.wefinance/data.json` or workspace fallback
2. Verify write permissions: Storage auto-falls back to workspace if home is unwritable
3. Check JSON format: Invalid JSON corrupts storage (handled gracefully)
4. Clear corrupted storage: Delete `~/.wefinance/data.json` manually

**Common issues**:
- `PermissionError`: Fallback to workspace storage (check logs)
- Data not persisting: Check `save_to_storage()` return value (bool)
- Corrupted JSON: `_load_all()` returns empty dict on parse failure

## Performance Considerations

### LLM API Calls

- **Vision OCR**: ~2-5 seconds per image (acceptable for demo, limits to 10 images/upload)
- **Chat**: ~1-3 seconds per message (cached queries return instantly)
- **Recommendations**: ~3-7 seconds (cached by input hash via `@st.cache_data`)
- **Timeouts**: All calls protected by @safe_call (30s vision, 15s chat/recommendations)

**Optimization opportunities**:
- Implement progressive loading for long transaction lists
- Pre-cache common queries on startup (e.g., "我这个月还能花多少？")
- Batch multiple images in single Vision API call (if API supports)

### Caching Strategy

1. **Query-level** (`chat_manager.py`): LRU cache for exact query matches (20 items)
2. **Deterministic inputs** (`@st.cache_data`): Recommendation generation (transaction hash)
3. **Session state**: All transaction data lives in session, not re-fetched
4. **Persistent storage** (`storage.py`): User preferences, trusted merchants (file-based)

**Cache invalidation**:
- Chat cache: Cleared on locale switch (different language = different response)
- `@st.cache_data`: Cleared automatically by Streamlit on input change
- Session state: Persists until browser refresh or explicit reset
- Storage: Persists until manual deletion or `clear_all_storage()`

### Streamlit Optimization

**Current performance**:
- Initial page load: ~2-3 seconds (includes I18n initialization)
- Page navigation: <1 second (session state persists)
- OCR upload: 2-5 seconds per image (API call)

**Best practices**:
- Use `@st.cache_data` for expensive computations
- Avoid re-running entire app on every interaction (use callbacks)
- Limit number of widgets per page (current: ~10-15 per page)

## Security Notes

### API Key Management

- **NEVER** commit `.env` file to version control
- Use `.env.example` as template for other developers
- API keys loaded via `python-dotenv` in all services
- Validate API key presence at service initialization (raises `ValueError` if missing)
- Error handling masks API key details in user-facing messages

### Input Validation

- **Transaction amounts**: Validated in Pydantic models (`models/entities.py`)
- **File uploads**: Limited to PNG/JPG in Streamlit uploader (`accept_multiple_files=True`)
- **User inputs**: Sanitized before LLM prompts (no injection attacks)
- **Date format**: Validated via regex in Transaction model

### Privacy

- **Images**: Processed locally (base64 encoded for API call), not stored permanently
- **Transactions**: Stored in session state only (cleared on browser refresh)
- **Persistent data**: Stored in local JSON file (~/.wefinance/data.json), no cloud upload
- **LLM provider**: `newapi.deepwisdom.ai` may log API calls - inform users in production
- **No database**: Zero cloud storage = zero data breach risk for MVP
- **Storage encryption**: Not implemented (local file is unencrypted JSON)

## Project Structure

```
WeFinance/
├── app.py                      # Streamlit entry point
├── environment.yml             # Conda environment (Python 3.10 + dependencies)
├── requirements.txt            # pip dependencies (latest versions)
├── .env.example               # Environment variable template
├── .env                       # Environment variables (git-ignored)
│
├── pages/                     # Streamlit pages (one file = one navigation item)
│   ├── __init__.py
│   ├── bill_upload.py         # Upload bills, run Vision OCR
│   ├── spending_insights.py   # Consumption analysis, anomaly detection
│   ├── advisor_chat.py        # AI financial advisor chat
│   └── investment_recs.py     # Explainable investment recommendations
│
├── modules/                   # Core business logic
│   ├── __init__.py
│   ├── analysis.py           # Data analysis, anomaly detection algorithms
│   └── chat_manager.py       # Chat context assembly, LLM call, caching
│
├── services/                  # AI service layer
│   ├── __init__.py
│   ├── vision_ocr_service.py  # GPT-4o Vision OCR (core innovation)
│   ├── ocr_service.py         # OCR facade (delegates to VisionOCRService)
│   ├── structuring_service.py # Legacy GPT-4o structuring (deprecated)
│   ├── recommendation_service.py # Investment recommendation generation
│   └── langchain_agent.py     # LangChain agent wrapper (optional)
│
├── models/                    # Data models (Pydantic)
│   ├── __init__.py
│   └── entities.py           # Transaction, UserProfile, etc.
│
├── utils/                     # Utilities
│   ├── __init__.py
│   ├── session.py            # Session state helpers (CRITICAL)
│   ├── i18n.py               # Internationalization engine
│   ├── error_handling.py     # Unified error handling (NEW)
│   └── storage.py            # File-based persistence (NEW)
│
├── locales/                   # Translation files
│   ├── zh_CN.json            # Chinese translations
│   └── en_US.json            # English translations
│
├── tests/                     # Test suite (pytest)
│   ├── __init__.py
│   ├── test_integration.py    # End-to-end scenarios
│   ├── test_ocr_service.py    # Vision OCR tests
│   ├── test_chat_manager.py   # Chat manager tests
│   ├── test_session_state.py  # Session state tests
│   ├── test_error_handling.py # Error handling tests (NEW)
│   ├── test_storage.py        # Storage tests (NEW)
│   ├── test_structuring_service.py # Legacy tests
│   └── test_i18n.py           # i18n tests
│
├── assets/                    # Static assets
│   └── sample_bills/          # Sample bill images for testing
│       ├── bill_dining.png
│       ├── bill_mixed.png
│       └── bill_shopping.png
│
├── screenshots/               # Demo materials for competition (NEW)
│   ├── 01_homepage_progress_zh.png
│   ├── 02_bill_upload_ocr_zh.png
│   ├── 03_spending_insights_zh.png
│   ├── 04_advisor_chat_zh.png
│   ├── 05_investment_recs_zh.png
│   ├── 06_sidebar_zh.png
│   ├── 07_homepage_progress_en.png
│   └── 08_advisor_chat_en.png
│
├── demo/                      # Presentation materials (NEW)
│   ├── wefinance_presentation.pptx
│   ├── video_script.md
│   ├── ppt_outline.md
│   └── checklist.md
│
├── .claude/                   # Project documentation
│   ├── PROJECT_RULES.md       # Claude Code ↔ Codex collaboration rules
│   └── specs/
│       └── wefinance-copilot/
│           ├── 00-repo-scan.md
│           ├── 01-product-requirements.md
│           ├── 02-system-architecture.md
│           └── 03-sprint-plan.md
│
├── generate_sample_bills.py   # Generate Chinese sample bills
├── generate_sample_bills_english.py # Generate English sample bills
└── test_vision_ocr.py         # Manual Vision OCR testing script
```

## For More Information

- **Project Overview**: See README.md
- **Collaboration Rules**: See `.claude/PROJECT_RULES.md`
- **System Architecture**: See `.claude/specs/wefinance-copilot/02-system-architecture.md`
- **Product Requirements**: See `.claude/specs/wefinance-copilot/01-product-requirements.md`
- **Sprint Planning**: See `.claude/specs/wefinance-copilot/03-sprint-plan.md`
- **Demo Checklist**: See `demo/checklist.md`

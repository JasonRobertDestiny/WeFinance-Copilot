# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WeFinance Copilot is an AI-powered financial assistant for the 2025 Shenzhen Fintech Competition. It uses Vision LLM (GPT-4o) for bill OCR, conversational AI for financial advice, and explainable AI for investment recommendations.

**Key Architecture Decision**: Originally used PaddleOCR, but migrated to GPT-4o Vision OCR for 100% recognition accuracy (vs 0% with synthetic images). This is the core competitive advantage.

**Project Roles**: See `.claude/PROJECT_RULES.md` for Claude Code and Codex collaboration workflow. Claude Code provides architecture/design, Codex implements.

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

**Current Coverage**: 58% (target 70%+). Weak spots: `chat_manager.py` (48%), `session.py` (36%), `vision_ocr_service.py` (no tests yet).

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

**Note**: PaddlePaddle dependencies remain in `environment.yml` for legacy compatibility but are no longer used in production code.

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

### LLM Integration Patterns

**Three LLM use cases**:

1. **Vision OCR** (`services/vision_ocr_service.py:60-160`):
   - Model: GPT-4o Vision
   - Input: Image bytes (base64 encoded)
   - Output: Structured JSON → List[Transaction]
   - Temperature: 0.0 (deterministic)
   - Prompt engineering: Specifies exact JSON format, valid categories, date format
   - Error handling: Returns empty list on failure (graceful degradation)

2. **Chat** (`modules/chat_manager.py`):
   - Model: GPT-4o (text)
   - Input: User query + transaction context + budget context
   - Output: Natural language financial advice
   - Caching: Query-level LRU cache (20 items, exact string match)
   - Context assembly: `_assemble_context()` formats transactions for prompt

3. **Recommendations** (`services/recommendation_service.py`):
   - Model: GPT-4o (text)
   - Input: Transactions + risk profile + investment goal
   - Output: Structured recommendation with reasoning chain (explainable AI)
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
except Exception as e:
    logger.error(f"OCR failed: {e}")
    return []  # NOT: raise

# LLM timeout → Use fallback response
except TimeoutError:
    return cached_or_default_response()  # NOT: raise
```

**Why**: User experience > perfect execution. Always provide a fallback path.

**User-facing error messages**:
- Translated via i18n system: `i18n.t("errors.api_key_missing")`
- Logged at appropriate levels: `logger.error()`, `logger.warning()`, `logger.info()`
- Never expose API keys, stack traces, or internal details to users

### Test Coverage Requirements

**Current status**: 58% coverage, target 70%+

**Weak spots**:
- `modules/chat_manager.py`: 48% (needs fallback, cache, whitelist tests)
- `utils/session.py`: 36% (needs session init, locale switch, persistence tests)
- `services/vision_ocr_service.py`: NEW FILE, no tests yet (high priority)

**Testing Vision OCR**:
```python
# Use mocking to avoid real API calls
from unittest.mock import patch, MagicMock

@patch('services.vision_ocr_service.OpenAI')
def test_extract_transactions(mock_openai):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = '[{"date": "2025-11-01", ...}]'
    mock_openai.return_value.chat.completions.create.return_value = mock_response

    service = VisionOCRService()
    transactions = service.extract_transactions_from_image(b'fake_image')

    assert len(transactions) == 1
    assert transactions[0].date == "2025-11-01"
```

**Test organization**:
- `tests/test_integration.py`: End-to-end user scenarios (upload → analyze → chat → recommend)
- `tests/test_ocr_service.py`: OCR service unit tests (vision OCR mocking)
- `tests/test_chat_manager.py`: Chat manager unit tests (cache, context assembly)
- `tests/test_session_state.py`: Session state helpers
- `tests/test_structuring_service.py`: Legacy structuring service (deprecated)
- `tests/test_i18n.py`: Internationalization tests

## Configuration

### Required .env Variables
```bash
# OpenAI-compatible API (REQUIRED)
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_BASE_URL=https://newapi.deepwisdom.ai/v1
OPENAI_MODEL=gpt-4o

# Optional: LLM provider selection (currently only supports openai)
LLM_PROVIDER=openai

# Legacy PaddleOCR config (not used in Vision OCR pipeline)
PADDLE_OCR_USE_ANGLE_CLASS="True"
PADDLE_OCR_LANG="ch"
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
- PaddlePaddle (legacy) requires specific Python version
- Consistent environment across development machines

**Environment structure**:
- Conda packages: numpy, pandas, scipy, opencv, pillow, plotly, pytest, black, ruff
- Pip packages: streamlit, paddleocr, paddlepaddle, openai, langchain
- Mixed installation: Use conda for scientific libs, pip for Python-only packages

**IMPORTANT**: Always activate environment before running any command:
```bash
conda activate wefinance
```

**Updating dependencies**:
1. Modify `environment.yml`
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

### 6. Missing Timeout on LLM Calls

**Current issue**: No timeout set on LLM API calls (Task 5 in backlog).

**Risk**: Hangs indefinitely if API is slow/unavailable.

**TODO**: Add `timeout=30` to all LLM calls:
```python
# In vision_ocr_service.py, chat_manager.py, recommendation_service.py
response = self.client.chat.completions.create(
    model=self.model,
    messages=[...],
    timeout=30,  # Add this
)
```

## Architecture Decisions Log

### 2025-11-06: PaddleOCR → GPT-4o Vision

**Problem**: PaddleOCR couldn't recognize synthetic bill images (0% accuracy on `generate_sample_bills.py` output).

**Solution**: Replaced with GPT-4o Vision, achieving 100% accuracy.

**Impact**:
- Removed PaddlePaddle dependency from production code (still in `environment.yml` for compatibility)
- Simplified pipeline from 2-step to 1-step
- Increased API cost (~$0.01/image) but acceptable for MVP/competition
- Improved accuracy from 0% to 100% on synthetic images

**Files Changed**:
- NEW: `services/vision_ocr_service.py` (161 lines)
- MODIFIED: `services/ocr_service.py` (now delegates to VisionOCRService)
- DEPRECATED: PaddleOCR usage (kept for backward compatibility, not used)

**Migration path**: All code uses `OCRService` facade, which internally delegates to `VisionOCRService`.

### 2025-11-06: Codex Collaboration Model

**Decision**: Claude Code provides architecture/design, Codex implements.

**Rationale**:
- Claude Code: Better at analysis, design, code review (Linus philosophy)
- Codex: Better at bulk implementation, repetitive tasks

**Process**: See `.claude/PROJECT_RULES.md` for detailed workflow.

**Key principles**:
1. Linus's Three Questions: Real problem? Simpler way? What breaks?
2. Claude Code generates detailed prompts for Codex
3. Codex implements and reports back
4. Claude Code reviews before user acceptance

## Debugging Tips

### Vision OCR Not Working

1. Check `.env` has valid `OPENAI_API_KEY`
2. Test API connectivity: `python test_vision_ocr.py`
3. Check logs: `services/vision_ocr_service.py` logs at INFO level
4. Verify image format: PNG/JPG/JPEG only (PDF not supported by Vision API)
5. Check API rate limits: `https://newapi.deepwisdom.ai/v1` may have limits

**Common errors**:
- `ValueError: OPENAI_API_KEY environment variable not set`: Missing/invalid `.env` file
- `JSONDecodeError`: Vision LLM returned malformed JSON (check logs for raw response)
- Empty transaction list: Image might not contain recognizable bill data

### Streamlit Session State Issues

1. Check `utils/session.py` for state initialization: `init_session_state()` called in `app.py:207`
2. Use `st.session_state` debugger: Add `st.write(st.session_state)` temporarily
3. Verify state keys match between pages: Use constants from `utils/session.py::DEFAULT_STATE`
4. Check session persistence: Session state resets on browser refresh (expected behavior)

**Common issues**:
- `KeyError: 'transactions'`: `init_session_state()` not called before access
- Data not persisting: Check if using helper functions, not direct dict access
- Locale not switching: Missing `st.rerun()` after `switch_locale()`

### LLM Timeout/Failure

1. Check API rate limits: `https://newapi.deepwisdom.ai/v1` dashboard
2. Verify network connectivity to OpenAI-compatible endpoint
3. Review fallback mechanisms in `chat_manager.py` and `recommendation_service.py`
4. Check API key validity: Test with `curl` or `python test_vision_ocr.py`

**Graceful degradation**:
- Vision OCR: Returns empty list, allows manual input
- Chat: Uses cached response if available
- Recommendations: Returns empty list, shows error message

### Test Failures

1. Activate conda environment first: `conda activate wefinance`
2. Check test isolation: Each test should be independent (no shared state)
3. Mock external dependencies: LLM APIs, file I/O (use `@patch`)
4. Run single test for debugging: `pytest tests/test_file.py::test_function -v`
5. Check test data: Sample bills in `assets/sample_bills/`, fixtures in `tests/`

**Common test failures**:
- `ModuleNotFoundError`: Conda environment not activated
- `AssertionError`: Expected behavior changed (update test or fix code)
- API call errors: Mock not working, real API being called (use `@patch`)

## Performance Considerations

### LLM API Calls

- **Vision OCR**: ~2-5 seconds per image (acceptable for demo, limits to 10 images/upload)
- **Chat**: ~1-3 seconds per message (cached queries return instantly)
- **Recommendations**: ~3-7 seconds (cached by input hash via `@st.cache_data`)

**Optimization opportunities**:
- Add `timeout=30` to all LLM calls (prevents hangs)
- Implement progressive loading for long transaction lists
- Pre-cache common queries on startup (e.g., "我这个月还能花多少？")

### Caching Strategy

1. **Query-level** (`chat_manager.py`): LRU cache for exact query matches (20 items)
2. **Deterministic inputs** (`@st.cache_data`): Recommendation generation (transaction hash)
3. **Session state**: All transaction data lives in session, not re-fetched

**Cache invalidation**:
- Chat cache: Cleared on locale switch (different language = different response)
- `@st.cache_data`: Cleared automatically by Streamlit on input change
- Session state: Persists until browser refresh or explicit reset

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

### Input Validation

- **Transaction amounts**: Validated in Pydantic models (`models/entities.py`)
- **File uploads**: Limited to PNG/JPG/PDF in Streamlit uploader (`accept_multiple_files=True`)
- **User inputs**: Sanitized before LLM prompts (no injection attacks)
- **Date format**: Validated via regex in Transaction model

### Privacy

- **Images**: Processed locally (base64 encoded for API call), not stored permanently
- **Transactions**: Stored in session state only (cleared on browser refresh)
- **LLM provider**: `newapi.deepwisdom.ai` may log API calls - inform users in production
- **No database**: Zero persistent storage = zero data breach risk for MVP

## Project Structure

```
WeFinance/
├── app.py                      # Streamlit entry point (303 lines)
├── environment.yml             # Conda environment (Python 3.10 + dependencies)
├── requirements.txt            # pip extras (pytest-cov, etc.)
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
│   └── i18n.py               # Internationalization engine
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
│   ├── test_structuring_service.py # Legacy tests
│   └── test_i18n.py           # i18n tests
│
├── assets/                    # Static assets
│   └── sample_bills/          # Sample bill images for testing
│       ├── bill_dining.png
│       ├── bill_mixed.png
│       └── bill_shopping.png
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
- **Testing Coverage**: Run `pytest --cov` and review `htmlcov/index.html`

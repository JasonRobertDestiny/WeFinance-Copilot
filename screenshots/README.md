# WeFinance Screenshot Playbook

This guide turns the requirements from `CODEX_TASK3_PROMPT.md` into a concrete capture plan that anyone on the team can follow without re-reading the full prompt. Work through the checklists in order and tick them off as you go.

## 0. Environment Prep

1. `conda activate wefinance`
2. `streamlit run app.py --server.headless false` (keep the terminal open)
3. Chrome → open `http://localhost:8501`
4. DevTools → `Ctrl+Shift+M` → `Dimensions: 1920 × 1080`
5. Hide bookmarks/address bar (F11 full-screen)

## 1. Data Seeding Checklist

| Step | Action | Verification |
| --- | --- | --- |
| 1 | Upload `assets/sample_bills/bill_mixed.png` | Bill Upload page lists 4 transactions |
| 2 | Sidebar → 月度预算 = `8000` | Budget badge shows `¥8,000` |
| 3 | Spending Insights page | Charts render + anomaly cards visible |
| 4 | Advisor Chat | Ask “我这个月超支了吗？应该如何调整？” then “餐饮支出占比是否合理？” → two answers |
| 5 | Investment Recs | Risk answers (稳健型), Goal “养老储备”, click 生成 → recommendation + charts |

## 2. Capture Spec

Store files under `screenshots/` using PNG (no compression). Target size <2 MB. Use `Ctrl+Shift+P → Capture screenshot` or OS hotkeys.

| # | File | Language | Scene & Notes |
| --- | --- | --- | --- |
| 1 | `01_homepage_progress_zh.png` | zh | Homepage title + 4-step cards; Steps 1-2 ✅, 3-4 ⭕; “开始 →” button visible |
| 2 | `02_bill_upload_ocr_zh.png` | zh | Bill Upload while `st.status` is expanded mid-processing (ideally file 2/3) showing previews |
| 3 | `03_spending_insights_zh.png` | zh | Spending Insights charts, anomaly callouts, trusted merchant widget |
| 4 | `04_advisor_chat_zh.png` | zh | Advisor Chat with 2–3 turns plus budget info pill |
| 5 | `05_investment_recs_zh.png` | zh | Recommendation summary, pie chart, metrics, rationale steps |
| 6 | `06_sidebar_settings_zh.png` | zh | Focus on sidebar: language selector, navigation radio, budget input, data management buttons |
| 7 | `07_homepage_en.png` | en | Homepage after switching language to English; repeat Step 1 framing |
| 8 | `08_advisor_chat_en.png` | en | Advisor Chat interface in English showing at least one Q&A pair |

### Framing Tips

- Scroll so key cards are centered; avoid cut-off components.
- Keep Streamlit toast/balloon overlays out of frame.
- For #6, use browser zoom 110 % to make sidebar readable while keeping at least the page hero visible in the background.

## 3. QA Before Commit

- [ ] All files exist in `screenshots/`.
- [ ] Resolution exactly 1920×1080 (check via file properties).
- [ ] File size <2 MB (re-capture with lower OS DPI if needed).
- [ ] Naming strictly matches table above.
- [ ] Quick visual sweep for typos, placeholder text, or sensitive data.

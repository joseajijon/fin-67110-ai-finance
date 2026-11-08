# Checkpoint 1 package

## Desk

- `equity_desk.py`: seven deterministic SEC steps and four separate OpenAI model-role calls.
- `requirements.txt`: official OpenAI Python SDK.
- `tests/`: selection, tag, arithmetic, release parsing and Costco known-answer tests.
- `README.md`: exact install and run commands.

## Partner-company proof

- Company: WD-40 Company (`WDFC`).
- Reported this month: Item 2.02 Form 8-K filed October 21, 2026.
- Earnings accession: `0000105132-26-000086`.
- Latest annual accession: `0000105132-26-000091`.
- Saved evidence, peer facts and report: `runs/WDFC_fallback_20261029/`.
- Mode: course-permitted fallback because the coding terminal could not reach SEC EDGAR.

## Verification

- Five automated tests pass.
- The saved report has the five required sections.
- The saved report states all eleven required audit claims.
- JSON evidence files parse successfully.
- `.env`, `.venv`, `.uv-cache`, `__pycache__`, and `*.pyc` are excluded.
- Human audit completed: 0 wrong or unsupported claims; 0 missing core claims.
- Partner Martin Gee checked claims 2 (revenue growth) and 3 (operating income and operating margin).
- Peer margins use GAAP operating income divided by GAAP net sales; three peer rows remain for the student's required hand audit.
- `.env` is excluded and is not part of this package.

This is a learning exercise, not financial advice.

AI assistance: Codex. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.

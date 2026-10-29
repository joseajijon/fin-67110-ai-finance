# Checkpoint 1 package

## Desk

- `equity_desk.py`: seven deterministic SEC steps and four separate OpenAI model-role calls.
- `requirements.txt`: official OpenAI Python SDK.
- `tests/`: selection, tag, arithmetic, release parsing and Costco known-answer tests.
- `README.md`: exact install and run commands.

## Partner-company proof

- Company: The Coca-Cola Company (`KO`).
- Reported this month: Item 2.02 Form 8-K filed October 27, 2026.
- Earnings accession: `0001628280-26-067403`.
- Latest annual accession: `0001628280-26-010047`.
- Saved evidence and report: `runs/KO_fallback_20261028/`.
- Mode: course-permitted fallback because the coding terminal could not reach SEC EDGAR.

## Verification

- Five automated tests pass.
- The saved report has the five required sections.
- The saved report states all eleven required audit claims.
- JSON evidence files parse successfully.
- `.env`, `.venv`, `.uv-cache`, `__pycache__`, and `*.pyc` are excluded.
- The student must complete `report_audit.md` by hand and have the partner check two claims.

This is a learning exercise, not financial advice.

AI assistance: Codex. Human source verification and judgment sign-off are still required before submission.

Any remaining errors are my own.

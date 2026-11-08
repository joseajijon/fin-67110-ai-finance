# Checkpoint 2 package — the verifier

## Exact Brightspace item

Submit one permanent GitHub commit link in `Brightspace -> Checkpoint 2`.
Do not upload a ZIP unless the instructor tells you to do that.

## What the commit contains

- `agent_team.py`: the fixed graph in code.
- `verifier.py`: exact XBRL, line, and arithmetic checks.
- `roles/`: one instruction file for each node.
- `app.py`: the Streamlit page.
- `tests/`: 6 passing automated tests, including the seeded-EPS test.
- `runs/COST_seeded_error_checkpoint2/verified_report.md`: the required verifier marks.
- `runs/COST_seeded_error_checkpoint2/verifier_marks.json`: the same marks in machine-readable form.
- `runs/COST_seeded_error_checkpoint2/10-K.txt`: the saved filing evidence.
- `runs/COST_seeded_error_checkpoint2/facts.json`: the saved XBRL evidence.

## Seeded-error known answer

- Seeded report value: annual GAAP diluted EPS of `$21.76`.
- Saved XBRL value: `$20.76`.
- Tag: `EarningsPerShareDiluted`.
- Period end: `2026-08-30`.
- Filing accession: `0000909832-26-000093`.
- Verifier mark: `wrong`.
- Correction: `$20.76`.
- Saved 10-K evidence: line 765 of `10-K.txt` contains `Diluted | $ | 20.76 | ... | $ | 18.21`.
- Total errors: `1`.
- Missing fixed claims: `0`.

The API account returned HTTP 429 because it has no credits. The Verifier still ran
all exact code checks and saved the required marks. The semantic model subcheck
recorded the provider error in `verifier_semantic_review.md`.

## Student-only item before claiming Lab 05 completion

The course says that AI must not write the three analyst personas. Replace the three
baseline analyst files in `roles/` with your own six-part personas. Use
`roles/PERSONA_WORKSHEET.md`. This manual item is not part of the seeded-error known
answer, but it is required to claim completion of Lab 05.

## Final public-repository check

Open the GitHub repository while logged out. Confirm that `.env`, `.venv`,
`.uv-cache`, `__pycache__`, and API keys are absent.

This is a learning exercise, not financial advice.

AI assistance: Codex. I verified the sources myself; the judgments are mine.

Any remaining errors are my own.

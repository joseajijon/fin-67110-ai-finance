# FIN 67110 Equity Research Desk

This project implements Lab 02's seven deterministic SEC steps and Lab 03's four model roles. The production program contains no company name. A ticker is always a command-line argument.

## Setup

Install the official OpenAI SDK in the project environment:

```bash
UV_CACHE_DIR="$PWD/.uv-cache" uv pip install --python .venv/bin/python -r requirements.txt
source .venv/bin/activate
```

Edit `.env` locally. Never upload it:

```text
API_KEY=your-openai-developer-key
SEC_USER_AGENT="Your Name your-purdue-email@purdue.edu"
```

## Lab 02: seven data steps, no model

Replace `P` with the dated closing price used in class:

```bash
python equity_desk.py COST --peers WMT,TGT,BJ --price 992.13
```

Run one step only:

```bash
python equity_desk.py COST --step 4
```

The complete run saves filing text, Exhibit 99.1, facts, ratios, release lines, peer facts, and filing metadata under `runs/COMPANY_TIMESTAMP/`.

## Lab 03: four model roles and report

```bash
python equity_desk.py COST --peers WMT,TGT,BJ --price 992.13 --report
```

The script prints each role name. It saves `equity_research_report.md`, `role_outputs.json`, and `report_audit.md` in the run folder. Complete `report_audit.md` by hand. The course prohibits AI from assigning the audit marks.

Run the same command on the ticker selected by your partner. Choose suitable peers and a dated price:

```bash
python equity_desk.py TICKER --peers PEER1,PEER2,PEER3 --price P --report
```

The OpenAI API is separate from a ChatGPT subscription. If the API account has no
credit, use the course fallback report procedure. A fallback report counts for
Checkpoint 1. Do not commit or upload `.env`.

## Checkpoint 1

Push the program, tests, saved COST and WMT folders, the partner-selected report,
and its audit file. Submit the permanent GitHub commit link in Brightspace under
`Week 2 -> Checkpoint 1`. Never upload `.env`, `.venv`, or `.uv-cache`.

## Evidence rules

- Each XBRL number includes its tag, period end, and filing accession.
- Each ratio includes its definition and arithmetic.
- The earnings 8-K is the latest 8-K reporting Item 2.02, not simply the latest 8-K.
- Revenue-tag selection prefers the candidate tag whose newest annual period is newest.
- All current facts must match the latest 10-K fiscal year end.
- `.env` is excluded from Git and GitHub.

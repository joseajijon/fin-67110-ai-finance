# Week 4 prework status

## Completed in code

- The closes reader has two functions: official closes between dates and the last close before a filing time.
- It uses an LSEG desktop session and `TR.ClosePrice`, or an export path from `.env`.
- A missing ticker returns `not available`, and the agent team continues.
- The agent team reads the EDGAR acceptance time. `--filed` overrides it in Eastern time.
- Only the Financial Analyst receives the selected close through the existing valuation input.
- Project-local seeker, worksheet, and discovery-test skills exist under `.codex/skills/`.
- The Stop hook checks evidence markers for numbers in declared skill output.
- A filing-backed reference for the two Form 10 checks is in `research/form10_checks.md`.

## Requires LSEG access

- Put `LSEG_APP_KEY` in `.env`, or put an absolute export path outside this repository in `LSEG_EXPORT_PATH`.
- Run one close and compare it with the exchange's official close for that date.

## Student-authored requirements

The course page says that AI must not write the following items. Complete them by hand:

- the one-line Greenblatt answer;
- the one-line Klarman answer;
- the by-hand EDGAR verification of both Form 10 examples in `research/form10_checks.md`;
- each factor, its direction, its chapter source, and the screen window in `student_inputs/factors.json`;
- the valuation method, rates, client purchase size, and conviction rules in `student_inputs/worksheet_method.json`;
- all six persona parts in `student_inputs/investor_persona.md`;
- the fresh-chat, tools-off cutoff test and the provider cutoff record;
- the team's live release choice and operator;
- the team's Thursday ownership choice.
- the personal reading of the skills and hooks pages, followed by review and trust of this repository's hook through `/hooks`.

Do not mark these items complete until you write or decide them yourself.

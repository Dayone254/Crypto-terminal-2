# Archived development scripts

These are one-off debug / inspection / cleanup scripts that accumulated in
`backend/` during development. They were moved here during the audit so they are
no longer:

- linted as part of `backend/` by `ruff check backend/ tests/`, and
- shipped inside the importable `tpt` package.

They are kept for reference only. They are **not** imported by the application
and are **not** covered by the test suite. Several of them (`clean_*.py`,
`scrub.py`) mutate data, so read before running.

Contains:
- `tpt_test_db.py`, `tpt_test_insert.py`, `tpt_data_test.py`, `tpt_data_test2.py`
  — previously inside `backend/tpt/` and `backend/tpt/data/`
- everything else that lived directly under `backend/*.py`

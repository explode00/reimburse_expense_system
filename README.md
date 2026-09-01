# Reimburse — expense reimbursement system

A small Flask + SQLite application implementing the requested workflow: employee-owned reports, itemized expenses, assigned approvers, server-enforced lifecycle transitions, immutable history, bulk decisions, reimbursement CSV export, dashboard metrics, and stale approval alerts.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

Demo accounts (created automatically on first run):
- `employee@example.com` / `password`
- `approver@example.com` / `password`
- `approver2@example.com` / `password`

Environment variables:
- `SECRET_KEY` — Flask session signing key (set this in production)
- `EXPENSE_DB` — SQLite database path
- `STALE_DAYS` — days in Submitted before an alert (default 3)
- `ALERT_REAPPEAR_DAYS` — days after dismissal before a still-undecided alert returns (default 3)

## Notes on enforcement

- Ownership, approver role, report status, self-approval/self-rejection/self-payment, and assigned-approver checks occur on the server.
- Report totals come from `SUM(expense_lines.amount_cents)` and cannot be set by clients.
- Expense edits and deletes are allowed only while the owner is in Draft.
- Rejection requires a reason and moves the report back to Draft.
- The `history` table is append-only from the application: there are no routes to edit or delete history records.
- Search/filter/sort/pagination are SQL-backed rather than browser-side.
- Bulk decisions process every selected report individually and return per-report successes/refusals, including the specific self-approval/refusal message.
- Approved reports not yet Paid form the reimbursement due amount and CSV export.

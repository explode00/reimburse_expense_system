# Reimburse — Expense Reimbursement System

A small Flask + SQLite application that replaces email-based expense reimbursement with a server-enforced workflow.

## Scenario alignment

The app is designed around the stated operating model:

- Employees create and own their own expense reports and line items.
- Approvers can see the company queue, plus a view filtered to reports assigned to them.
- The server prevents an approver from approving, rejecting, or paying a report they own.
- Rejection is recorded as an immutable Submitted -> Rejected event with a reason, then the report immediately returns to Draft so the owner can fix and resubmit it.
- Report totals are calculated from expense lines on the server.
- Active Submitted and Approved reports cannot be archived, preventing operational work or unpaid reimbursements from disappearing from default views.
- Dashboard numbers are scoped correctly: employees see only their own reimbursement activity, while approvers see the company-wide operational picture.
- Stale approval alerts can be dismissed by an assigned approver and reappear after the configured interval; a fresh resubmission starts a fresh alert cycle.

## Roles

Demo users are seeded automatically on a new database:

- employee@example.com / password
- approver@example.com / password
- approver2@example.com / password

## Run

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

## Configuration

Environment variables:

- `SECRET_KEY` — Flask session secret
- `EXPENSE_DB` — SQLite database path
- `STALE_DAYS` — days before a Submitted report is considered stale (default 3)
- `ALERT_REAPPEAR_DAYS` — days after dismissal before a stale alert reappears (default 3)
- `PORT` — HTTP port (default 5000)

## Tests

```bash
python -m unittest discover -s tests -v
```

The included tests cover server-calculated totals, self-approval blocking, rejection/resubmission behavior, and per-report bulk-action refusals.

## Important production hardening still recommended

This demo intentionally stays small. A production deployment should add CSRF protection, stronger session/security settings, secure secrets, database migrations, structured audit logging, rate limiting, receipt uploads/object storage, email notifications, and a dedicated finance/payment role if finance needs privileges distinct from approvers.

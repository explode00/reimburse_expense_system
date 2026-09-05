# Submission

Fill this in and commit it. This is the first file we open.

## Links

- ****GitHub repository:**** <https://github.com/explode00/reimburse_expense_system>

- ****Live application:**** https://busytest.pythonanywhere.com

## Notes for the reviewer

The application is deployed on PythonAnywhere's free tier.

The application uses SQLite and is seeded with demo data.

The free-tier deployment may take a little longer to respond after a period of inactivity.

## Demo credentials

| Role | Email | Password |

|------|-------|----------|

| Employee | `<employee@example.com>` | `<password>` |

| Approver | `<approver@example.com>` | `<password>` |

## Stack

| Layer | What you used | Why |

|-------|---------------|-----|

| Frontend | Flask server-rendered HTML/CSS | Keeps the application simple and allows the core workflow to stay in one codebase. |

| Backend | Python / Flask | Provides the HTTP API, authentication, authorization, workflow rules, server-side filtering, reporting, and CSV export. |

| Database | SQLite | Lightweight relational database suitable for this assignment and simple deployment. |

| Hosting | PythonAnywhere | Provides a simple free-tier deployment for the Flask application. |

## Goal checklist

Mark each honestly. Partial is fine — say what is partial.

| # | Goal | Status | Notes |

|---|------|--------|-------|

| 1 | Accounts and roles | Done | Employees and approvers authenticate with email/password. Approver capabilities are enforced server-side, including prevention of approvers acting on their own reports. |

| 2 | Expense reports | Done | Employees create reports with title/date range, edit drafts, and archive/restore reports without deleting history. |

| 3 | Expense lines | Done | Reports contain individual dated expense lines with amount, fixed category, and description. Totals are calculated server-side from the lines. |

| 4 | Report lifecycle with rules | Done | Supports Draft → Submitted → Approved/Rejected → Paid, with ownership/role checks and required rejection reasons. Rejected reports return to Draft for correction and resubmission. |

| 5 | Assigned approvers | Done | Reports can have multiple eligible approvers, while approvers can also view the full submitted queue and filter to their assignments. |

| 6 | Finding reports | Done | Search, status/owner/approver filters, sorting, pagination, and total match counts are performed server-side. |

| 7 | Acting on many reports at once | Done | Bulk approve/reject operations return per-report results, including self-ownership refusals. Approved unpaid reports can be exported as CSV. |

| 8 | Dashboard | Done | Dashboard includes approval, reimbursement, approval-this-week, and payment-this-week metrics, status/category breakdowns, and an eight-week paid reimbursement chart. |

| 9 | Immutable history | Done | Report timelines record status changes, actors, rejection reasons, and comments without allowing later edits/deletions. |

| 10 | Stale-approval alerts | Done | Submitted reports become stale after the configured threshold. Assigned approvers can dismiss alerts, and alerts return if the report remains undecided for the configured reappearance period. |

## How much time did you actually spend?

Roughly 12 Hours

## What would you do next, with another 12 hours?

I would focus on production hardening and usability. In particular, I would replace SQLite with a managed PostgreSQL database, add automated tests for the full lifecycle and permission matrix, improve authentication and session security, add receipt attachments, and add email notifications for submission, rejection, approval, payment, and stale approvals. I would also improve the finance experience with stronger reimbursement reporting and clearer payment reconciliation.

## What are you least happy with in this codebase, and why?

The biggest compromise is the use of SQLite and the relatively lightweight deployment architecture. That keeps the assignment simple and inexpensive, but it is not the architecture I would choose for a production reimbursement system with multiple concurrent users and stronger operational requirements. I would also spend more time separating business logic from route handlers and expanding automated test coverage so that the workflow rules are easier to maintain as the system grows.

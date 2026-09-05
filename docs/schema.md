# Schema

Answer each of these, in your own words.

* Table by table: what columns and types does each one have?

`users`

* `id` — INTEGER, primary key, auto-incrementing
* `email` — TEXT, unique and required
* `password_hash` — TEXT, required
* `role` — TEXT, restricted to `employee` or `approver`
* `created_at` — TEXT, required

`reports`

* `id` — INTEGER, primary key, auto-incrementing
* `owner_id` — INTEGER, required, foreign key to `users`
* `title` — TEXT, required
* `start_date` — TEXT, required
* `end_date` — TEXT, required
* `status` — TEXT, restricted to Draft, Submitted, Approved, Rejected, or Paid
* `submitted_at` — TEXT, nullable
* `approved_at` — TEXT, nullable
* `paid_at` — TEXT, nullable
* `archived` — INTEGER, restricted to 0 or 1
* `created_at` — TEXT, required
* `updated_at` — TEXT, required

`expense_lines`

* `id` — INTEGER, primary key, auto-incrementing
* `report_id` — INTEGER, required, foreign key to `reports`
* `expense_date` — TEXT, required
* `amount_cents` — INTEGER, required and greater than zero
* `category` — TEXT, required
* `description` — TEXT, required

`report_approvers`

* `report_id` — INTEGER, required, foreign key to `reports`
* `approver_id` — INTEGER, required, foreign key to `users`
* Composite primary key on `report_id` and `approver_id`

`history`

* `id` — INTEGER, primary key, auto-incrementing
* `report_id` — INTEGER, required, foreign key to `reports`
* `actor_id` — INTEGER, foreign key to `users`
* `event_type` — TEXT, restricted to `status_change` or `comment`
* `old_status` — TEXT, nullable
* `new_status` — TEXT, nullable
* `reason` — TEXT, nullable
* `comment` — TEXT, nullable
* `created_at` — TEXT, required

`alert_dismissals`

* `id` — INTEGER, primary key, auto-incrementing

* `report_id` — INTEGER, required, foreign key to `reports`

* `approver_id` — INTEGER, required, foreign key to `users`

* `dismissed_at` — TEXT, required

* Unique constraint on `report_id` and `approver_id`

* Which relationships are one-to-many, and which are many-to-many?

`users → reports` is one-to-many because one user can own many reports.

`reports → expense_lines` is one-to-many because one report can contain many expense lines.

`reports ↔ users` through `report_approvers` is many-to-many because one report can have multiple eligible approvers and one approver can be assigned to multiple reports.

`reports → history` is one-to-many because each report can accumulate many immutable history entries.

`reports ↔ approvers` through `alert_dismissals` is effectively a many-to-many event relationship, although the uniqueness rule allows only one current dismissal record per report/approver pair.

* Which constraints are enforced by the database, and which by application code — and why did you draw the line there?

The database enforces structural rules such as required fields, uniqueness, allowed role/status/event values, positive expense amounts, foreign-key relationships, and the composite/unique keys.

Application code enforces business workflow rules because they depend on the current authenticated user and the current state of a report. Examples include who may submit, whether an approver is assigned, preventing an approver from acting on their own report, requiring a rejection reason, and which status transitions are legal.

I kept business-policy rules in application code because they require request context and workflow logic, while relational integrity belongs in the database.

* What did you deliberately denormalise?

The report stores `submitted_at`, `approved_at`, and `paid_at` rather than deriving every timestamp from the history table. This makes common dashboard and list queries simpler and avoids repeatedly searching history for the latest transition.

The report total is not stored at all. It is deliberately calculated from `expense_lines` so the client cannot set a conflicting total.

* What would break first if this had 100x the data?

The first pressure points would be large report-list queries, dashboard aggregations, and history/alert lookups. More indexes and query tuning would be needed, and SQLite would become a limiting factor for concurrent writes. At that point I would move the database to PostgreSQL, review query plans, add more targeted indexes, and consider caching or precomputed reporting data for dashboard queries.

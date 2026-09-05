# AI prompts

The prompts below record the requests used during development, in the order they were used, grouped by what I was trying to achieve. AI output was reviewed and corrected against the assignment requirements and the running application.

## Build the initial system

### Prompt

"Build the system that replaces the email thread" using the supplied expense reimbursement scenario and all ten required goals, including accounts/roles, report and line-item management, lifecycle rules, approver assignment, server-side search/filtering, bulk actions, CSV export, dashboard reporting, immutable history, and stale-approval alerts.

### What you got

A Flask application using SQLite with server-rendered templates, authentication, report and expense-line CRUD, lifecycle routes, approver assignment, dashboards, reporting, CSV export, history, alerts, and seeded demo accounts.

### What you corrected

I reviewed the implementation against the exact requirements and identified areas where the workflow needed tightening, especially server-side ownership checks, self-approval prevention, immutable history, stale-alert behaviour, and scenario-specific lifecycle rules.

## Debug the Flask startup problem

### Prompt

The application failed with `RuntimeError: Working outside of application context` because `seed_demo()` called database helpers that use Flask's `g` before an application context existed. Fix the startup problem.

### What you got

The database seeding code was changed so initialization and seeding run inside `app.app_context()` when the application starts.

### What you corrected

I verified that the startup path, CLI path, and hosted WSGI path need to be treated differently. The final code keeps `app.run()` under `if __name__ == "__main__"` and performs initialization/seeding inside an application context.

## Align the implementation more closely with the scenario

### Prompt

"Can it be bettered and more aligned with the proposed scenario" with emphasis on the real finance workflow and the exact requirements in the assignment.

### What you got

The implementation was tightened around employee-versus-approver visibility, approval queue behaviour, rejection, archiving, stale alerts, and dashboard scope.

### What you corrected

I specifically corrected cases where:

* employee dashboards could expose information outside the employee's own scope,
* rejection did not fully follow the required return-to-Draft workflow,
* stale alerts did not correctly account for a new submission cycle,
* active Submitted/Approved reports could be archived and disappear from finance workflow views.

I also added stronger workflow tests for server-side rules.

## Fix and verify workflow edge cases

### Prompt

Review the application against the ten requirements and make sure illegal transitions and bulk decisions are rejected with clear per-report messages, including self-owned reports.

### What you got

Workflow guards were centralised in the transition logic, and bulk actions now process each report independently and return individual success/refusal results.

### What you corrected

I verified that a report owned by the acting approver is rejected specifically with the self-approval/self-rejection message instead of being treated as a generic failure.

## Correct an initially wrong lifecycle interpretation

### Prompt

Re-check the rejection requirement: a rejected report must record the rejection reason and then return to Draft so the owner can edit and submit it again.

### What you got

The implementation records both status changes in immutable history: `Submitted → Rejected` with the rejection reason, followed by `Rejected → Draft`.

### What you corrected

The rejection workflow was changed from treating Rejected as a terminal state to treating the rejection as a recorded decision that immediately reopens the report for correction.

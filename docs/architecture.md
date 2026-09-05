# Architecture

Answer each of these, in your own words, once the system has taken real shape.

* What are the moving pieces, and how do they talk to each other?

The application is a small server-rendered Flask application.

The browser talks to Flask over HTTP. Flask handles authentication, authorization, report and expense-line operations, workflow transitions, search/filtering, dashboard queries, CSV export, comments, history, and stale-alert logic.

Flask talks directly to the SQLite database using Python's built-in `sqlite3` module. Templates render the server-provided data back to the browser.

There is also a small JSON endpoint for retrieving a report's server-calculated total.

* Where does each piece run?

The browser-side HTML/CSS runs in the user's web browser.

The Flask application runs on the PythonAnywhere web server using the Flask application object through the hosting platform's WSGI configuration.

The SQLite database is stored alongside the deployed application.

* What is the request path for one representative user action, end to end?

For an employee submitting a report:

1. The employee signs in and Flask stores the authenticated user's ID in the session.
2. The employee creates a Draft report and adds expense lines.
3. When Submit is requested, Flask loads the report from SQLite and checks that the authenticated user is the owner.
4. Flask calculates the total directly from the expense lines and checks that the report has at least one expense and at least one assigned approver.
5. Flask performs the allowed `Draft → Submitted` transition and records an immutable history entry.
6. Flask commits the transaction to SQLite.
7. The browser is redirected to the report/detail or reports view.
8. An approver subsequently sees the report in the approval queue. When the approver decides, the server again checks role, ownership, assignment, and current status before changing the report and recording the decision in history.

* What did you decide *not* to build, and why?

I did not build receipt image uploads and OCR, mileage calculation, multi-currency support, multi-level approval chains, corporate-card reconciliation, recurring expense templates, or department budget-versus-actual reporting.

Those were optional stretch ideas. I prioritised the ten required goals so the core reimbursement workflow, server-side authorization, reporting, audit history, and stale-alert behaviour were completed first.

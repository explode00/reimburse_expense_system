# Plan

Answer each of these, in your own words.

* How did you break the work into sessions?

I broke the work into a small number of focused sessions: first the core data model and authentication, then expense report and line-item workflows, then the approval lifecycle and role enforcement, followed by reporting/dashboard features, and finally testing, deployment, and cleanup.

* What order did you build in, and why that order?

I started with the database schema and authentication because almost every later requirement depends on identifying the current user and enforcing ownership. I then built report and expense-line CRUD, followed by the report lifecycle because submission, approval, rejection, and payment are the core business rules. After that I added approver assignment, server-side search/filtering, bulk actions, CSV export, dashboard metrics, history, and stale alerts. I finished by adding workflow tests and fixing deployment/startup issues.

* What did you estimate versus what it actually took?

I estimated roughly 12 hours based on the assignment's suggested time budget. The actual time spent was also soomewhat 12 hours.


The parts that took more iteration than expected were the lifecycle edge cases, especially self-approval protection, rejection returning a report to Draft, stale-alert behaviour, and getting the application running correctly under a hosted Flask environment.

* What did you cut when you ran short?

I did not implement the optional stretch ideas such as receipt OCR, mileage calculation, multi-currency support, multi-level approval chains, corporate-card reconciliation, recurring templates, or department budget reporting. I prioritised completing the ten required goals instead.

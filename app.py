import csv
import io
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, g, jsonify, make_response, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("EXPENSE_DB", BASE_DIR / "expenses.db"))
STALE_DAYS = int(os.environ.get("STALE_DAYS", "3"))
ALERT_REAPPEAR_DAYS = int(os.environ.get("ALERT_REAPPEAR_DAYS", "3"))
CATEGORIES = ["Travel", "Meals", "Supplies", "Lodging", "Ground Transport", "Other"]
STATUSES = ["Draft", "Submitted", "Approved", "Rejected", "Paid"]

app = Flask(__name__)
app.config.update(SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-this"))

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('employee','approver')),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id INTEGER NOT NULL REFERENCES users(id),
  title TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('Draft','Submitted','Approved','Rejected','Paid')) DEFAULT 'Draft',
  submitted_at TEXT,
  approved_at TEXT,
  paid_at TEXT,
  archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS expense_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  expense_date TEXT NOT NULL,
  amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
  category TEXT NOT NULL,
  description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS report_approvers (
  report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  approver_id INTEGER NOT NULL REFERENCES users(id),
  PRIMARY KEY(report_id, approver_id)
);
CREATE TABLE IF NOT EXISTS history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  actor_id INTEGER REFERENCES users(id),
  event_type TEXT NOT NULL CHECK(event_type IN ('status_change','comment')),
  old_status TEXT,
  new_status TEXT,
  reason TEXT,
  comment TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alert_dismissals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  approver_id INTEGER NOT NULL REFERENCES users(id),
  dismissed_at TEXT NOT NULL,
  UNIQUE(report_id, approver_id)
);
CREATE INDEX IF NOT EXISTS idx_reports_owner ON reports(owner_id);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);
CREATE INDEX IF NOT EXISTS idx_reports_submitted_at ON reports(submitted_at);
CREATE INDEX IF NOT EXISTS idx_lines_report ON expense_lines(report_id);
CREATE INDEX IF NOT EXISTS idx_history_report ON history(report_id, created_at);
CREATE INDEX IF NOT EXISTS idx_dismissals ON alert_dismissals(report_id, approver_id, dismissed_at);
"""


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def money(cents):
    return f"${cents / 100:,.2f}"


@app.template_filter("money")
def money_filter(cents):
    return money(cents or 0)


@app.before_request
def load_user():
    g.user = None
    user_id = session.get("user_id")
    if user_id:
        g.user = query_one("SELECT id, email, role FROM users WHERE id=?", (user_id,))


@app.context_processor
def inject_globals():
    alerts_count = len(alert_reports_for(g.user['id'])) if getattr(g, 'user', None) and g.user['role']=='approver' else 0
    return {"categories": CATEGORIES, "statuses": STATUSES, "stale_days": STALE_DAYS, "alert_reappear_days": ALERT_REAPPEAR_DAYS, "alerts_count": alerts_count}


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def query_one(sql, args=()):
    return db().execute(sql, args).fetchone()


def query_all(sql, args=()):
    return db().execute(sql, args).fetchall()


@app.teardown_appcontext
def close_db(exception=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def seed_demo():
    if query_one("SELECT 1 FROM users LIMIT 1"):
        return
    created = now_iso()
    users = [
        ("employee@example.com", generate_password_hash("password"), "employee", created),
        ("approver@example.com", generate_password_hash("password"), "approver", created),
        ("approver2@example.com", generate_password_hash("password"), "approver", created),
    ]
    db().executemany("INSERT INTO users(email,password_hash,role,created_at) VALUES(?,?,?,?)", users)
    db().commit()


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not g.user:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def approver_required(view):
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if g.user["role"] != "approver":
            abort(403)
        return view(*args, **kwargs)
    return wrapper


def report_or_404(report_id):
    report = query_one("SELECT * FROM reports WHERE id=?", (report_id,))
    if not report:
        abort(404)
    return report


def can_view_report(report):
    return g.user and (report["owner_id"] == g.user["id"] or g.user["role"] == "approver")


def require_report_view(report):
    if not can_view_report(report):
        abort(403)


def is_assigned(report_id, approver_id):
    return query_one("SELECT 1 FROM report_approvers WHERE report_id=? AND approver_id=?", (report_id, approver_id)) is not None


def total_cents(report_id):
    row = query_one("SELECT COALESCE(SUM(amount_cents),0) AS total FROM expense_lines WHERE report_id=?", (report_id,))
    return int(row["total"])


def add_history(report_id, actor_id, event_type, old_status=None, new_status=None, reason=None, comment=None):
    db().execute(
        "INSERT INTO history(report_id,actor_id,event_type,old_status,new_status,reason,comment,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (report_id, actor_id, event_type, old_status, new_status, reason, comment, now_iso()),
    )


def transition(report_id, new_status, actor_id, reason=None):
    report = report_or_404(report_id)
    old = report["status"]
    if old == new_status:
        raise ValueError(f"Report is already {new_status}.")
    allowed = {
        "Draft": {"Submitted"},
        "Submitted": {"Approved", "Rejected"},
        "Approved": {"Paid"},
        "Rejected": set(),
        "Paid": set(),
    }
    if new_status not in allowed[old]:
        raise ValueError(f"Cannot move report from {old} to {new_status}.")
    actor = query_one("SELECT id, role FROM users WHERE id=?", (actor_id,))
    if not actor:
        raise ValueError("Acting user does not exist.")
    if new_status == "Submitted":
        if report["owner_id"] != actor_id:
            raise ValueError("Only the report owner can submit this report.")
        if total_cents(report_id) <= 0:
            raise ValueError("A report must contain at least one expense line before submission.")
        if not query_one("SELECT 1 FROM report_approvers WHERE report_id=?", (report_id,)):
            raise ValueError("Assign at least one eligible approver before submitting this report.")
    if new_status in {"Approved", "Rejected"}:
        if actor["role"] != "approver":
            raise ValueError("Only an approver can decide a submitted report.")
        if report["owner_id"] == actor_id:
            raise ValueError("You cannot approve or reject a report you own; it must wait for a different approver.")
        if not is_assigned(report_id, actor_id):
            raise ValueError("You are not assigned as an eligible approver for this report.")
        if new_status == "Rejected" and not reason:
            raise ValueError("A rejection reason is required.")
    if new_status == "Paid":
        if actor["role"] != "approver":
            raise ValueError("Only an approver can mark a report paid.")
        if report["owner_id"] == actor_id:
            raise ValueError("You cannot mark your own report as paid.")
        if not is_assigned(report_id, actor_id):
            raise ValueError("You are not assigned as an eligible approver for this report.")

    ts = now_iso()
    if new_status == "Rejected":
        # Rejection is a recorded decision, then immediately returns the report
        # to Draft so the owner can correct and resubmit it. Both status changes
        # are immutable history entries.
        db().execute("UPDATE reports SET status='Draft', updated_at=?, submitted_at=NULL, approved_at=NULL WHERE id=?", (ts, report_id))
        add_history(report_id, actor_id, "status_change", "Submitted", "Rejected", reason=reason)
        add_history(report_id, actor_id, "status_change", "Rejected", "Draft", reason="Returned to draft after rejection")
    else:
        values = {"status": new_status, "updated_at": ts}
        if new_status == "Submitted":
            values["submitted_at"] = ts
            values["approved_at"] = None
            values["paid_at"] = None
        elif new_status == "Approved":
            values["approved_at"] = ts
        elif new_status == "Paid":
            values["paid_at"] = ts
        set_clause = ", ".join(f"{k}=?" for k in values)
        db().execute(f"UPDATE reports SET {set_clause} WHERE id=?", [*values.values(), report_id])
        add_history(report_id, actor_id, "status_change", old, new_status, reason=reason)
    db().commit()


def validate_report_dates(title, start_date, end_date):
    if not title.strip():
        raise ValueError("Title is required.")
    start = parse_date(start_date)
    end = parse_date(end_date)
    if end < start:
        raise ValueError("End date cannot be before start date.")


def alert_reports_for(approver_id):
    cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)
    rows = query_all(
        """SELECT r.*, u.email AS owner_email
           FROM reports r
           JOIN users u ON u.id=r.owner_id
           JOIN report_approvers ra ON ra.report_id=r.id AND ra.approver_id=?
           WHERE r.status='Submitted' AND r.submitted_at <= ?
           ORDER BY r.submitted_at ASC""",
        (approver_id, cutoff.isoformat()),
    )
    result = []
    now = datetime.now(timezone.utc)
    for r in rows:
        d = query_one(
            "SELECT dismissed_at FROM alert_dismissals WHERE report_id=? AND approver_id=?",
            (r["id"], approver_id),
        )
        if not d:
            result.append(r)
            continue
        dismissed = datetime.fromisoformat(d["dismissed_at"])
        submitted = datetime.fromisoformat(r["submitted_at"])
        # A new submission starts a fresh alert cycle. Otherwise a dismissal
        # suppresses the alert only for ALERT_REAPPEAR_DAYS.
        if submitted > dismissed or dismissed + timedelta(days=ALERT_REAPPEAR_DAYS) <= now:
            result.append(r)
    return result


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = query_one("SELECT * FROM users WHERE email=?", (email,))
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    scope = "WHERE 1=1" if g.user["role"] == "approver" else "WHERE owner_id=?"
    scope_args = () if g.user["role"] == "approver" else (g.user["id"],)
    counts = {}
    counts["awaiting"] = query_one(f"SELECT COUNT(*) c FROM reports {scope} AND status='Submitted'", scope_args)["c"]
    counts["due"] = query_one(
        f"SELECT COALESCE(SUM(t.total_cents),0) total FROM reports r LEFT JOIN (SELECT report_id,SUM(amount_cents) total_cents FROM expense_lines GROUP BY report_id) t ON t.report_id=r.id {scope.replace('owner_id', 'r.owner_id')} AND r.status='Approved'",
        scope_args,
    )["total"]
    week_start = (datetime.now(timezone.utc).date() - timedelta(days=datetime.now(timezone.utc).weekday())).isoformat()
    counts["approved_week"] = query_one(f"SELECT COUNT(*) c FROM reports {scope} AND approved_at >= ? AND status IN ('Approved','Paid')", (*scope_args, week_start))["c"]
    counts["paid_week"] = query_one(f"SELECT COUNT(*) c FROM reports {scope} AND paid_at >= ? AND status='Paid'", (*scope_args, week_start))["c"]
    status_counts = query_all(f"SELECT status, COUNT(*) c FROM reports {scope} GROUP BY status ORDER BY status", scope_args)
    category_counts = query_all(
        f"""SELECT l.category, COUNT(*) c, COALESCE(SUM(l.amount_cents),0) total_cents
             FROM expense_lines l JOIN reports r ON r.id=l.report_id
             {scope.replace('owner_id','r.owner_id')} GROUP BY l.category ORDER BY total_cents DESC, l.category""",
        scope_args,
    )
    eight_weeks = []
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    for i in range(7, -1, -1):
        start = monday - timedelta(weeks=i)
        end = start + timedelta(days=7)
        row = query_one(
            f"SELECT COALESCE(SUM((SELECT SUM(amount_cents) FROM expense_lines l WHERE l.report_id=r.id)),0) total FROM reports r {scope.replace('owner_id','r.owner_id')} AND r.status='Paid' AND paid_at >= ? AND paid_at < ?",
            (*scope_args, start.isoformat(), end.isoformat()),
        )
        eight_weeks.append({"label": start.isoformat(), "total": row["total"]})
    alerts = alert_reports_for(g.user["id"]) if g.user["role"] == "approver" else []
    return render_template(
        "dashboard.html",
        counts=counts,
        status_counts=status_counts,
        category_counts=category_counts,
        eight_weeks=eight_weeks,
        alerts=alerts,
        my_assignments=(query_one("SELECT COUNT(*) c FROM reports r JOIN report_approvers ra ON ra.report_id=r.id WHERE ra.approver_id=? AND r.status='Submitted'", (g.user["id"],))["c"] if g.user["role"]=='approver' else 0),
    )


@app.route("/reports")
@login_required
def reports():
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(50, max(5, int(request.args.get("per_page", 10))))
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    owner_id = request.args.get("owner_id", "")
    approver_id = request.args.get("approver_id", "")
    assigned = request.args.get("assigned", "")
    sort = request.args.get("sort", "submitted")
    direction = request.args.get("direction", "desc").lower()
    if direction not in {"asc", "desc"}:
        direction = "desc"
    sort_sql = {
        "submitted": "r.submitted_at",
        "status": "r.status",
        "total": "total_cents",
    }.get(sort, "r.submitted_at")

    where = ["r.archived=0"]
    if request.args.get('include_archived') == '1':
        where = ["1=1"]
    args = []
    if g.user["role"] != "approver":
        where.append("r.owner_id=?")
        args.append(g.user["id"])
    else:
        # Approvers can see their own reports plus other employees' reports; decisions are still server-gated.
        pass
    if search:
        where.append("r.title LIKE ?")
        args.append(f"%{search}%")
    if status:
        if status not in STATUSES:
            abort(400)
        where.append("r.status=?")
        args.append(status)
    if owner_id:
        where.append("r.owner_id=?")
        args.append(owner_id)
    if approver_id:
        where.append("EXISTS (SELECT 1 FROM report_approvers rax WHERE rax.report_id=r.id AND rax.approver_id=?)")
        args.append(approver_id)
    if assigned == "me" and g.user["role"] == "approver":
        where.append("EXISTS (SELECT 1 FROM report_approvers rax2 WHERE rax2.report_id=r.id AND rax2.approver_id=?)")
        args.append(g.user["id"])
    where_sql = " AND ".join(where)
    base = f"""FROM reports r JOIN users ou ON ou.id=r.owner_id
              LEFT JOIN (SELECT report_id, SUM(amount_cents) total_cents FROM expense_lines GROUP BY report_id) t ON t.report_id=r.id
              WHERE {where_sql}"""
    total = query_one(f"SELECT COUNT(*) c {base}", args)["c"]
    offset = (page - 1) * per_page
    rows = query_all(
        f"SELECT r.*, ou.email AS owner_email, COALESCE(t.total_cents,0) total_cents {base} ORDER BY {sort_sql} {direction} NULLS LAST, r.id DESC LIMIT ? OFFSET ?",
        [*args, per_page, offset],
    )
    owners = query_all("SELECT id,email FROM users WHERE id=? ORDER BY email", (g.user["id"],)) if g.user["role"]=="employee" else query_all("SELECT id,email FROM users ORDER BY email")
    approvers = query_all("SELECT id,email FROM users WHERE role='approver' ORDER BY email")
    return render_template("reports.html", reports=rows, owners=owners, approvers=approvers, total=total, page=page, per_page=per_page, filters=request.args)


@app.route("/reports/new", methods=["GET", "POST"])
@login_required
def new_report():
    if request.method == "POST":
        try:
            validate_report_dates(request.form.get("title", ""), request.form.get("start_date", ""), request.form.get("end_date", ""))
            ts = now_iso()
            cur = db().execute("INSERT INTO reports(owner_id,title,start_date,end_date,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (g.user["id"], request.form["title"].strip(), request.form["start_date"], request.form["end_date"], "Draft", ts, ts))
            db().commit()
            return redirect(url_for("report_detail", report_id=cur.lastrowid))
        except Exception as e:
            flash(str(e), "error")
    return render_template("report_form.html", report=None)


@app.route("/reports/<int:report_id>")
@login_required
def report_detail(report_id):
    report = query_one("SELECT r.*, u.email AS owner_email FROM reports r JOIN users u ON u.id=r.owner_id WHERE r.id=?", (report_id,))
    if not report:
        abort(404)
    require_report_view(report)
    lines = query_all("SELECT * FROM expense_lines WHERE report_id=? ORDER BY expense_date, id", (report_id,))
    assignments = query_all("SELECT u.id,u.email FROM report_approvers ra JOIN users u ON u.id=ra.approver_id WHERE ra.report_id=? ORDER BY u.email", (report_id,))
    all_approvers = query_all("SELECT id,email FROM users WHERE role='approver' ORDER BY email")
    history_rows = query_all("SELECT h.*, u.email AS actor_email FROM history h LEFT JOIN users u ON u.id=h.actor_id WHERE h.report_id=? ORDER BY h.created_at, h.id", (report_id,))
    return render_template("report_detail.html", report=report, lines=lines, assignments=assignments, all_approvers=all_approvers, history_rows=history_rows, total=total_cents(report_id))


@app.route("/reports/<int:report_id>/edit", methods=["POST"])
@login_required
def edit_report(report_id):
    report = report_or_404(report_id)
    if report["owner_id"] != g.user["id"]:
        abort(403)
    if report["status"] != "Draft":
        flash("Only draft reports can be edited.", "error")
        return redirect(url_for("report_detail", report_id=report_id))
    try:
        validate_report_dates(request.form.get("title", ""), request.form.get("start_date", ""), request.form.get("end_date", ""))
        db().execute("UPDATE reports SET title=?,start_date=?,end_date=?,updated_at=? WHERE id=? AND status='Draft' AND owner_id=?", (request.form["title"].strip(), request.form["start_date"], request.form["end_date"], now_iso(), report_id, g.user["id"]))
        db().commit()
        flash("Report updated.", "ok")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("report_detail", report_id=report_id))


@app.route("/reports/<int:report_id>/submit", methods=["POST"])
@login_required
def submit_report(report_id):
    try:
        transition(report_id, "Submitted", g.user["id"])
        flash("Report submitted for approval.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("report_detail", report_id=report_id))


@app.route("/reports/<int:report_id>/archive", methods=["POST"])
@login_required
def archive_report(report_id):
    report = report_or_404(report_id)
    if report["owner_id"] != g.user["id"]:
        abort(403)
    if report["status"] in {"Submitted", "Approved"}:
        flash("Active reports cannot be archived while they are awaiting a decision or payment.", "error")
        return redirect(url_for("report_detail", report_id=report_id))
    db().execute("UPDATE reports SET archived=1,updated_at=? WHERE id=?", (now_iso(), report_id))
    db().commit()
    flash("Report archived.", "ok")
    return redirect(url_for("reports"))


@app.route("/reports/<int:report_id>/restore", methods=["POST"])
@login_required
def restore_report(report_id):
    report = report_or_404(report_id)
    if report["owner_id"] != g.user["id"]:
        abort(403)
    db().execute("UPDATE reports SET archived=0,updated_at=? WHERE id=?", (now_iso(), report_id))
    db().commit()
    flash("Report restored.", "ok")
    return redirect(url_for("report_detail", report_id=report_id))


@app.route("/reports/<int:report_id>/lines/add", methods=["POST"])
@login_required
def add_line(report_id):
    report = report_or_404(report_id)
    if report["owner_id"] != g.user["id"] or report["status"] != "Draft":
        abort(403)
    try:
        amount = round(float(request.form["amount"]) * 100)
        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")
        category = request.form["category"]
        if category not in CATEGORIES:
            raise ValueError("Invalid category.")
        parse_date(request.form["expense_date"])
        desc = request.form["description"].strip()
        if not desc:
            raise ValueError("Description is required.")
        db().execute("INSERT INTO expense_lines(report_id,expense_date,amount_cents,category,description) VALUES(?,?,?,?,?)", (report_id, request.form["expense_date"], amount, category, desc))
        db().execute("UPDATE reports SET updated_at=? WHERE id=?", (now_iso(), report_id))
        db().commit()
        flash("Expense added.", "ok")
    except (KeyError, ValueError) as e:
        flash(str(e), "error")
    return redirect(url_for("report_detail", report_id=report_id))


@app.route("/reports/<int:report_id>/lines/<int:line_id>/edit", methods=["POST"])
@login_required
def edit_line(report_id, line_id):
    report = report_or_404(report_id)
    if report["owner_id"] != g.user["id"] or report["status"] != "Draft":
        abort(403)
    line = query_one("SELECT * FROM expense_lines WHERE id=? AND report_id=?", (line_id, report_id))
    if not line:
        abort(404)
    try:
        amount = round(float(request.form["amount"]) * 100)
        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")
        category = request.form["category"]
        if category not in CATEGORIES:
            raise ValueError("Invalid category.")
        parse_date(request.form["expense_date"])
        desc = request.form["description"].strip()
        if not desc:
            raise ValueError("Description is required.")
        db().execute("UPDATE expense_lines SET expense_date=?,amount_cents=?,category=?,description=? WHERE id=? AND report_id=?", (request.form["expense_date"], amount, category, desc, line_id, report_id))
        db().execute("UPDATE reports SET updated_at=? WHERE id=?", (now_iso(), report_id))
        db().commit()
        flash("Expense updated.", "ok")
    except (KeyError, ValueError) as e:
        flash(str(e), "error")
    return redirect(url_for("report_detail", report_id=report_id))


@app.route("/reports/<int:report_id>/lines/<int:line_id>/delete", methods=["POST"])
@login_required
def delete_line(report_id, line_id):
    report = report_or_404(report_id)
    if report["owner_id"] != g.user["id"] or report["status"] != "Draft":
        abort(403)
    db().execute("DELETE FROM expense_lines WHERE id=? AND report_id=?", (line_id, report_id))
    db().execute("UPDATE reports SET updated_at=? WHERE id=?", (now_iso(), report_id))
    db().commit()
    flash("Expense removed.", "ok")
    return redirect(url_for("report_detail", report_id=report_id))


@app.route("/reports/<int:report_id>/assign", methods=["POST"])
@approver_required
def assign_approvers(report_id):
    report = report_or_404(report_id)
    require_report_view(report)
    ids = {int(x) for x in request.form.getlist("approver_ids")}
    valid = {r["id"] for r in query_all("SELECT id FROM users WHERE role='approver'")}
    if not ids.issubset(valid):
        abort(400)
    db().execute("DELETE FROM report_approvers WHERE report_id=?", (report_id,))
    db().executemany("INSERT INTO report_approvers(report_id,approver_id) VALUES(?,?)", [(report_id, i) for i in ids])
    db().commit()
    flash("Eligible approvers updated.", "ok")
    return redirect(url_for("report_detail", report_id=report_id))


@app.route("/reports/<int:report_id>/decide", methods=["POST"])
@approver_required
def decide_report(report_id):
    action = request.form.get("action")
    target = "Approved" if action == "approve" else "Rejected" if action == "reject" else None
    if not target:
        abort(400)
    try:
        transition(report_id, target, g.user["id"], reason=request.form.get("reason", "").strip() or None)
        flash(f"Report {target.lower()}.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("report_detail", report_id=report_id))


@app.route("/reports/<int:report_id>/paid", methods=["POST"])
@approver_required
def mark_paid(report_id):
    try:
        transition(report_id, "Paid", g.user["id"])
        flash("Report marked paid.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("report_detail", report_id=report_id))


@app.route("/reports/<int:report_id>/comment", methods=["POST"])
@login_required
def add_comment(report_id):
    report = report_or_404(report_id)
    require_report_view(report)
    comment = request.form.get("comment", "").strip()
    if not comment:
        flash("Comment cannot be empty.", "error")
    elif report["owner_id"] != g.user["id"] and g.user["role"] != "approver":
        abort(403)
    else:
        add_history(report_id, g.user["id"], "comment", comment=comment)
        db().commit()
        flash("Comment added.", "ok")
    return redirect(url_for("report_detail", report_id=report_id))


@app.route("/reports/bulk", methods=["POST"])
@approver_required
def bulk_action():
    action = request.form.get("action")
    report_ids = []
    for raw in request.form.getlist("report_ids"):
        try:
            report_ids.append(int(raw))
        except ValueError:
            pass
    results = []
    target = "Approved" if action == "approve" else "Rejected" if action == "reject" else None
    reason = request.form.get("reason", "").strip() or None
    if not report_ids:
        session["bulk_results"] = [("—", "No reports were selected.")]
        return redirect(url_for("reports"))
    if target == "Rejected" and not reason:
        session["bulk_results"] = [(rid, "refused: A rejection reason is required for bulk rejection.") for rid in report_ids]
        return redirect(url_for("reports"))
    if not target:
        flash("Unsupported bulk action.", "error")
        return redirect(url_for("reports"))
    for rid in report_ids:
        report = query_one("SELECT * FROM reports WHERE id=?", (rid,))
        if not report:
            results.append((rid, "refused: report not found"))
            continue
        try:
            transition(rid, target, g.user["id"], reason=reason)
            results.append((rid, "success"))
        except ValueError as e:
            results.append((rid, f"refused: {e}"))
    session["bulk_results"] = results
    return redirect(url_for("reports"))


@app.route("/reports/export.csv")
@approver_required
def export_csv():
    rows = query_all(
        """SELECT r.id,r.title,u.email AS owner_email,r.start_date,r.end_date,r.submitted_at,
                  COALESCE((SELECT SUM(amount_cents) FROM expense_lines l WHERE l.report_id=r.id),0) total_cents
           FROM reports r JOIN users u ON u.id=r.owner_id
           WHERE r.status='Approved' ORDER BY r.approved_at ASC"""
    )
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["report_id", "title", "owner_email", "start_date", "end_date", "submitted_at", "amount_due"])
    for r in rows:
        writer.writerow([r["id"], r["title"], r["owner_email"], r["start_date"], r["end_date"], r["submitted_at"], f"{r['total_cents']/100:.2f}"])
    response = make_response(out.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=reimbursements_due.csv"
    return response


@app.route("/alerts/<int:report_id>/dismiss", methods=["POST"])
@approver_required
def dismiss_alert(report_id):
    report = report_or_404(report_id)
    if report["status"] != "Submitted" or not is_assigned(report_id, g.user["id"]):
        abort(403)
    db().execute("INSERT INTO alert_dismissals(report_id,approver_id,dismissed_at) VALUES(?,?,?) ON CONFLICT(report_id,approver_id) DO UPDATE SET dismissed_at=excluded.dismissed_at", (report_id, g.user["id"], now_iso()))
    db().commit()
    return redirect(url_for("dashboard"))


@app.route("/api/reports/<int:report_id>/total")
@login_required
def api_total(report_id):
    report = report_or_404(report_id)
    require_report_view(report)
    return jsonify({"report_id": report_id, "total_cents": total_cents(report_id)})


@app.cli.command("init-db")
def init_db_command():
    with app.app_context():
        init_db()
        seed_demo()
    print(f"Initialized {DB_PATH}")


if __name__ == "__main__":
    with app.app_context():
        init_db()
        seed_demo()
    app.run(debug=True, host="127.0.0.1", port=int(os.environ.get("PORT", "5000")))

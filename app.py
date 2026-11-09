from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from pathlib import Path
import os

app = Flask(__name__)
app.secret_key = "change-this-secret-key-before-deployment"
DB_PATH = Path(__file__).with_name("food_donation.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','donor','receiver')),
            verified INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS donations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donor_id INTEGER NOT NULL,
            food_name TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            description TEXT,
            pickup_location TEXT NOT NULL,
            expiry TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'available',
            created_at TEXT NOT NULL,
            FOREIGN KEY(donor_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donation_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            message TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY(donation_id) REFERENCES donations(id),
            FOREIGN KEY(receiver_id) REFERENCES users(id)
        );
        """)
        # Demo admin account: admin@foodshare.com / Admin123!
        admin = db.execute("SELECT id FROM users WHERE email=?", ("admin@foodshare.com",)).fetchone()
        if not admin:
            db.execute(
                "INSERT INTO users(name,email,password,role,verified) VALUES(?,?,?,?,1)",
                ("System Admin", "admin@foodshare.com",
                 generate_password_hash("Admin123!"), "admin")
            )

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if session.get("role") not in roles:
                flash("You do not have permission to access that page.", "danger")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator

@app.route("/")
def index():
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM donations").fetchone()[0]
        available = db.execute(
            "SELECT COUNT(*) FROM donations WHERE status='available' AND expiry > ?",
            (datetime.now().strftime("%Y-%m-%dT%H:%M"),)
        ).fetchone()[0]
        completed = db.execute(
            "SELECT COUNT(*) FROM donations WHERE status='collected'"
        ).fetchone()[0]
    return render_template("index.html", total=total, available=available, completed=completed)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        if not name or not email or len(password) < 8 or role not in ("donor", "receiver"):
            flash("Enter valid details. Password must be at least 8 characters.", "danger")
            return render_template("register.html")
        try:
            with get_db() as db:
                db.execute(
                    "INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
                    (name, email, generate_password_hash(password), role)
                )
            flash("Account created. You can now log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("That email is already registered.", "danger")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        flash("Incorrect email or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    with get_db() as db:
        role = session["role"]
        if role == "admin":
            stats = {
                "donations": db.execute("SELECT COUNT(*) FROM donations").fetchone()[0],
                "available": db.execute("SELECT COUNT(*) FROM donations WHERE status='available' AND expiry>?", (now,)).fetchone()[0],
                "requests": db.execute("SELECT COUNT(*) FROM requests").fetchone()[0],
                "users": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                "collected": db.execute("SELECT COUNT(*) FROM donations WHERE status='collected'").fetchone()[0]
            }
            donations = db.execute("""
                SELECT d.*, u.name AS donor_name FROM donations d
                JOIN users u ON u.id=d.donor_id ORDER BY d.id DESC
            """).fetchall()
            users = db.execute("SELECT id,name,email,role,verified FROM users ORDER BY id DESC").fetchall()
            return render_template("admin_dashboard.html", stats=stats, donations=donations, users=users)

        if role == "donor":
            donations = db.execute(
                "SELECT * FROM donations WHERE donor_id=? ORDER BY id DESC",
                (session["user_id"],)
            ).fetchall()
            requests = db.execute("""
                SELECT r.*, d.food_name, u.name AS receiver_name
                FROM requests r JOIN donations d ON d.id=r.donation_id
                JOIN users u ON u.id=r.receiver_id
                WHERE d.donor_id=? ORDER BY r.id DESC
            """, (session["user_id"],)).fetchall()
            return render_template("donor_dashboard.html", donations=donations, requests=requests, now=now)

        donations = db.execute("""
            SELECT d.*, u.name AS donor_name FROM donations d
            JOIN users u ON u.id=d.donor_id
            WHERE d.status='available' AND d.expiry > ?
            ORDER BY d.expiry ASC
        """, (now,)).fetchall()
        my_requests = db.execute("""
            SELECT r.*, d.food_name FROM requests r
            JOIN donations d ON d.id=r.donation_id
            WHERE r.receiver_id=? ORDER BY r.id DESC
        """, (session["user_id"],)).fetchall()
    return render_template("receiver_dashboard.html", donations=donations, my_requests=my_requests)

@app.route("/donation/new", methods=["GET", "POST"])
@role_required("donor")
def new_donation():
    if request.method == "POST":
        food_name = request.form.get("food_name", "").strip()
        category = request.form.get("category", "").strip()
        location = request.form.get("pickup_location", "").strip()
        description = request.form.get("description", "").strip()
        expiry = request.form.get("expiry", "")
        try:
            quantity = int(request.form.get("quantity", "0"))
        except ValueError:
            quantity = 0
        now = datetime.now().strftime("%Y-%m-%dT%H:%M")
        if not all([food_name, category, location, expiry]) or quantity < 1 or expiry <= now:
            flash("Enter all required details, a positive quantity, and a future expiry time.", "danger")
            return render_template("new_donation.html")
        with get_db() as db:
            db.execute("""
                INSERT INTO donations(donor_id,food_name,category,quantity,description,
                                      pickup_location,expiry,created_at)
                VALUES(?,?,?,?,?,?,?,?)
            """, (session["user_id"], food_name, category, quantity, description,
                  location, expiry, now))
        flash("Food donation posted successfully.", "success")
        return redirect(url_for("dashboard"))
    return render_template("new_donation.html")

@app.route("/donation/<int:donation_id>/request", methods=["POST"])
@role_required("receiver")
def request_donation(donation_id):
    message = request.form.get("message", "").strip()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    with get_db() as db:
        donation = db.execute(
            "SELECT * FROM donations WHERE id=? AND status='available' AND expiry>?",
            (donation_id, now)
        ).fetchone()
        if not donation:
            flash("This donation is no longer available.", "danger")
            return redirect(url_for("dashboard"))
        existing = db.execute(
            "SELECT id FROM requests WHERE donation_id=? AND receiver_id=? AND status IN ('pending','accepted')",
            (donation_id, session["user_id"])
        ).fetchone()
        if existing:
            flash("You already have an active request for this donation.", "warning")
        else:
            db.execute(
                "INSERT INTO requests(donation_id,receiver_id,message,created_at) VALUES(?,?,?,?)",
                (donation_id, session["user_id"], message, now)
            )
            flash("Your request has been sent to the donor.", "success")
    return redirect(url_for("dashboard"))

@app.route("/request/<int:request_id>/<action>", methods=["POST"])
@role_required("donor")
def update_request(request_id, action):
    if action not in ("accepted", "rejected"):
        flash("Invalid request action.", "danger")
        return redirect(url_for("dashboard"))
    with get_db() as db:
        row = db.execute("""
            SELECT r.id, r.status, r.donation_id, d.donor_id, d.status AS donation_status
            FROM requests r JOIN donations d ON d.id=r.donation_id
            WHERE r.id=?
        """, (request_id,)).fetchone()
        if not row or row["donor_id"] != session["user_id"]:
            flash("Request not found or not yours.", "danger")
        elif row["status"] != "pending":
            flash("This request has already been processed.", "warning")
        elif action == "accepted" and row["donation_status"] != "available":
            flash("This donation is no longer available.", "danger")
        else:
            db.execute("UPDATE requests SET status=? WHERE id=?", (action, request_id))
            if action == "accepted":
                db.execute("UPDATE donations SET status='reserved' WHERE id=?", (row["donation_id"],))
                db.execute("""
                    UPDATE requests SET status='rejected'
                    WHERE donation_id=? AND id<>? AND status='pending'
                """, (row["donation_id"], request_id))
            flash(f"Request {action}.", "success")
    return redirect(url_for("dashboard"))

@app.route("/donation/<int:donation_id>/collected", methods=["POST"])
@role_required("donor", "receiver")
def mark_collected(donation_id):
    with get_db() as db:
        donation = db.execute("SELECT * FROM donations WHERE id=?", (donation_id,)).fetchone()
        if not donation:
            flash("Donation not found.", "danger")
        else:
            accepted = db.execute("""
                SELECT * FROM requests WHERE donation_id=? AND status='accepted'
            """, (donation_id,)).fetchone()
            allowed = (
                session["role"] == "donor" and donation["donor_id"] == session["user_id"]
            ) or (
                session["role"] == "receiver" and accepted and accepted["receiver_id"] == session["user_id"]
            )
            if not allowed or donation["status"] != "reserved":
                flash("Only the donor or accepted receiver can confirm this collection.", "danger")
            else:
                db.execute("UPDATE donations SET status='collected' WHERE id=?", (donation_id,))
                flash("Collection confirmed. Thank you for helping reduce food waste!", "success")
    return redirect(url_for("dashboard"))

@app.route("/admin/user/<int:user_id>/verify", methods=["POST"])
@role_required("admin")
def verify_user(user_id):
    with get_db() as db:
        db.execute("UPDATE users SET verified=1 WHERE id=? AND role='receiver'", (user_id,))
    flash("Receiver verification updated.", "success")
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
if __name__ == "__main__":
    init_db()
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
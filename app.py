import os
import pickle
import sqlite3
from datetime import datetime, timezone

import pandas as pd
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from email_validator import validate_email, EmailNotValidError

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

DB_PATH = os.path.join(os.path.dirname(__file__), "predictions_new.db")

# -----------------------------------------
# Valid input ranges
# -----------------------------------------
FIELD_RANGES = {
    "hours_studied": (0, 24, "Hours Studied"),
    "previous_scores": (0, 100, "Previous Scores"),
    "sleep_hours": (0, 24, "Sleep Hours"),
    "sample_papers": (0, 20, "Sample Question Papers Practiced"),
}

# -----------------------------------------
# Load trained model
# -----------------------------------------
with open("model.pkl", "rb") as file:
    model = pickle.load(file)

# -----------------------------------------
# Load scaler
# -----------------------------------------
with open("scaler.pkl", "rb") as file:
    scaler = pickle.load(file)


# -----------------------------------------
# Database setup with users table
# -----------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    
    # FIRST: Create users table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    
    # SECOND: Create predictions table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            hours_studied REAL NOT NULL,
            previous_scores REAL NOT NULL,
            extracurricular TEXT NOT NULL,
            sleep_hours REAL NOT NULL,
            sample_papers REAL NOT NULL,
            prediction REAL NOT NULL,
            message TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )
    
    # Create index
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_predictions_user_id 
        ON predictions (user_id)
        """
    )
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")


# -----------------------------------------
# User class for Flask-Login
# -----------------------------------------
class User(UserMixin):
    def __init__(self, id, username, email, password_hash, created_at):
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.created_at = created_at
    
    @staticmethod
    def get(user_id):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        conn.close()
        if row:
            return User(
                row['id'], row['username'], row['email'],
                row['password_hash'], row['created_at']
            )
        return None
    
    @staticmethod
    def get_by_username(username):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()
        if row:
            return User(
                row['id'], row['username'], row['email'],
                row['password_hash'], row['created_at']
            )
        return None
    
    @staticmethod
    def create(username, email, password):
        password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        created_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute(
            """
            INSERT INTO users (username, email, password_hash, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (username, email, password_hash, created_at)
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        
        return User.get(user_id)


@login_manager.user_loader
def load_user(user_id):
    return User.get(int(user_id))


init_db()


# -----------------------------------------
# Validation functions
# -----------------------------------------
def validate_inputs(form):
    parsed = {}
    
    for field, (min_val, max_val, label) in FIELD_RANGES.items():
        raw = form.get(field, "").strip()
        
        if raw == "":
            return None, f"{label} is required."
        
        try:
            value = float(raw)
        except ValueError:
            return None, f"{label} must be a number."
        
        if value < min_val or value > max_val:
            return None, f"{label} must be between {min_val} and {max_val}."
        
        parsed[field] = value
    
    extracurricular = form.get("extracurricular", "").strip()
    if extracurricular not in ("Yes", "No"):
        return None, "Please select an option for Extracurricular Activities."
    
    parsed["extracurricular"] = extracurricular
    
    return parsed, None


def validate_registration(form):
    username = form.get("username", "").strip()
    email = form.get("email", "").strip()
    password = form.get("password", "")
    confirm_password = form.get("confirm_password", "")
    
    # Username validation
    if not username or len(username) < 3:
        return None, "Username must be at least 3 characters long."
    
    if not username.isalnum():
        return None, "Username must contain only letters and numbers."
    
    # Email validation
    if not email:
        return None, "Email is required."
    
    try:
        valid = validate_email(email)
        email = valid.normalized
    except EmailNotValidError:
        return None, "Please enter a valid email address."
    
    # Password validation
    if not password or len(password) < 6:
        return None, "Password must be at least 6 characters long."
    
    if password != confirm_password:
        return None, "Passwords do not match."
    
    # Check if username already exists
    if User.get_by_username(username):
        return None, "Username already taken. Please choose another."
    
    # Check if email already exists
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT id FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    
    if row:
        return None, "An account with this email already exists."
    
    return {"username": username, "email": email, "password": password}, None


def get_performance_message(prediction):
    if prediction >= 90:
        return "Excellent Performance! 🏆"
    elif prediction >= 75:
        return "Very Good Performance! 💪"
    elif prediction >= 60:
        return "Good Performance! 👍"
    elif prediction >= 40:
        return "Average Performance. 📊"
    else:
        return "Needs Improvement. 📚"


# -----------------------------------------
# Database operations
# -----------------------------------------
def log_prediction(user_id, data, prediction, message):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO predictions (
            user_id, created_at, hours_studied, previous_scores,
            extracurricular, sleep_hours, sample_papers,
            prediction, message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            data["hours_studied"],
            data["previous_scores"],
            data["extracurricular"],
            data["sleep_hours"],
            data["sample_papers"],
            prediction,
            message,
        ),
    )
    conn.commit()
    conn.close()


def get_user_predictions(user_id, limit=20):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT * FROM predictions 
        WHERE user_id = ? 
        ORDER BY id DESC 
        LIMIT ?
        """,
        (user_id, limit)
    ).fetchall()
    conn.close()
    return rows


# -----------------------------------------
# Routes
# -----------------------------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        
        if not username or not password:
            flash("Please enter both username and password.", "danger")
            return render_template("login.html")
        
        user = User.get_by_username(username)
        
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user)
            next_page = request.args.get("next")
            flash(f"Welcome back, {user.username}!", "success")
            return redirect(next_page) if next_page else redirect(url_for("home"))
        else:
            flash("Invalid username or password.", "danger")
    
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    
    if request.method == "POST":
        data, error = validate_registration(request.form)
        
        if error:
            flash(error, "danger")
            return render_template(
                "register.html",
                username=request.form.get("username", ""),
                email=request.form.get("email", "")
            )
        
        user = User.create(data["username"], data["email"], data["password"])
        login_user(user)
        flash(f"Account created successfully! Welcome, {user.username}!", "success")
        return redirect(url_for("home"))
    
    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


@app.route("/predict", methods=["POST"])
@login_required
def predict():
    data, error = validate_inputs(request.form)
    
    if error:
        return render_template(
            "index.html",
            error=error,
            hours_studied=request.form.get("hours_studied", ""),
            previous_scores=request.form.get("previous_scores", ""),
            extracurricular=request.form.get("extracurricular", ""),
            sleep_hours=request.form.get("sleep_hours", ""),
            sample_papers=request.form.get("sample_papers", ""),
        )
    
    try:
        extracurricular_value = 1 if data["extracurricular"] == "Yes" else 0
        
        input_data = pd.DataFrame({
            "Hours Studied": [data["hours_studied"]],
            "Previous Scores": [data["previous_scores"]],
            "Extracurricular Activities": [extracurricular_value],
            "Sleep Hours": [data["sleep_hours"]],
            "Sample Question Papers Practiced": [data["sample_papers"]],
        })
        
        input_scaled = scaler.transform(input_data)
        
        prediction = model.predict(input_scaled)[0]
        prediction = round(float(prediction), 2)
        prediction = max(0.0, min(100.0, prediction))
        
        message = get_performance_message(prediction)
        
        log_prediction(current_user.id, data, prediction, message)
        
        return render_template(
            "index.html",
            prediction=prediction,
            message=message,
            hours_studied=data["hours_studied"],
            previous_scores=data["previous_scores"],
            extracurricular=data["extracurricular"],
            sleep_hours=data["sleep_hours"],
            sample_papers=data["sample_papers"],
        )
    
    except Exception as e:
        print("ERROR:", e)
        return render_template(
            "index.html",
            error=f"Prediction error: {str(e)}"
        )


@app.route("/history")
@login_required
def history():
    rows = get_user_predictions(current_user.id, limit=20)
    return render_template("history.html", predictions=rows)


@app.route("/api/predict", methods=["POST"])
@login_required
def api_predict():
    data, error = validate_inputs(request.form)
    
    if error:
        return jsonify({"error": error}), 400
    
    try:
        extracurricular_value = 1 if data["extracurricular"] == "Yes" else 0
        
        input_data = pd.DataFrame({
            "Hours Studied": [data["hours_studied"]],
            "Previous Scores": [data["previous_scores"]],
            "Extracurricular Activities": [extracurricular_value],
            "Sleep Hours": [data["sleep_hours"]],
            "Sample Question Papers Practiced": [data["sample_papers"]],
        })
        
        input_scaled = scaler.transform(input_data)
        
        prediction = model.predict(input_scaled)[0]
        prediction = round(float(prediction), 2)
        prediction = max(0.0, min(100.0, prediction))
        
        message = get_performance_message(prediction)
        
        log_prediction(current_user.id, data, prediction, message)
        
        return jsonify({
            "prediction": prediction,
            "message": message
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -----------------------------------------
# Run Flask application
# -----------------------------------------
if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
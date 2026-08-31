import os
import pickle
import sqlite3
from datetime import datetime, timezone

import pandas as pd
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "predictions.db")

# -----------------------------------------
# Valid input ranges (kept in sync with the
# min/max attributes in templates/index.html)
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
# Database setup
# -----------------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            hours_studied REAL NOT NULL,
            previous_scores REAL NOT NULL,
            extracurricular TEXT NOT NULL,
            sleep_hours REAL NOT NULL,
            sample_papers REAL NOT NULL,
            prediction REAL NOT NULL,
            message TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def log_prediction(data, prediction, message):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO predictions (
            created_at, hours_studied, previous_scores,
            extracurricular, sleep_hours, sample_papers,
            prediction, message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
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


def get_recent_predictions(limit=20):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM predictions ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows


init_db()


# -----------------------------------------
# Validation
# -----------------------------------------
def validate_inputs(form):
    """Parse and validate form input.

    Returns (data, error_message). data is None if error_message is set.
    """
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


def get_performance_message(prediction):
    """Get performance message based on prediction score."""
    if prediction >= 90:
        return "Excellent Performance!"
    elif prediction >= 75:
        return "Very Good Performance!"
    elif prediction >= 60:
        return "Good Performance!"
    elif prediction >= 40:
        return "Average Performance."
    else:
        return "Needs Improvement."


# -----------------------------------------
# Home page
# -----------------------------------------
@app.route("/")
def home():
    return render_template("index.html")


# -----------------------------------------
# Prediction
# -----------------------------------------
@app.route("/predict", methods=["POST"])
def predict():

    data, error = validate_inputs(request.form)

    if error:
        # Re-populate whatever the user typed, even if invalid,
        # so they don't have to retype everything.
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

        # -------------------------------------
        # Create input DataFrame
        # IMPORTANT:
        # Keep exactly the same feature order
        # used during training.
        # -------------------------------------
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

        # Clamp prediction to a valid Performance Index range (0-100)
        prediction = max(0.0, min(100.0, prediction))

        message = get_performance_message(prediction)

        log_prediction(data, prediction, message)

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


# -----------------------------------------
# Prediction history
# -----------------------------------------
@app.route("/history")
def history():
    rows = get_recent_predictions(limit=20)
    return render_template("history.html", predictions=rows)


# -----------------------------------------
# API endpoint for AJAX requests
# -----------------------------------------
@app.route("/api/predict", methods=["POST"])
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

        log_prediction(data, prediction, message)

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
# Student Performance Prediction

A Flask web app that predicts a student's Performance Index using a trained
Ridge regression model.

## Features

- Predicts a 0–100 Performance Index from 5 inputs (hours studied, previous
  score, extracurricular activities, sleep hours, sample papers practiced).
- **Input validation** on both the client (instant feedback) and server
  (source of truth) — out-of-range or missing values show a clear error
  instead of crashing.
- **Prediction history** — every prediction is logged to a local SQLite
  database and viewable at `/history`.
- Ready to deploy with `gunicorn` (see below).

## Project structure

```
Students_performance/
├── app.py                  # Flask application
├── model.pkl                # Trained Ridge regression model
├── scaler.pkl                # StandardScaler used on the 5 input features
├── requirements.txt
├── Procfile                  # For Render/Railway/Heroku-style deployment
├── .gitignore
├── templates/
│   ├── index.html            # Form + result page
│   └── history.html           # Prediction history page
└── static/
    └── style.css               # Page styling
```

`predictions.db` (SQLite) is created automatically the first time the app
runs — it's not included in the project and is git-ignored.

## Local setup

1. (Optional but recommended) create a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate      # Windows
   source venv/bin/activate   # macOS/Linux
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Run the app:
   ```
   python app.py
   ```

4. Open your browser to:
   ```
   http://127.0.0.1:5000/
   ```

5. View past predictions at:
   ```
   http://127.0.0.1:5000/history
   ```

By default the app runs with debug mode off. To enable Flask's debugger and
auto-reload while developing, set `FLASK_DEBUG=1` before running:
```
set FLASK_DEBUG=1         # Windows (cmd)
$env:FLASK_DEBUG=1        # Windows (PowerShell)
export FLASK_DEBUG=1      # macOS/Linux
python app.py
```

## Deployment

The app reads `PORT` from the environment (defaults to 5000) and binds to
`0.0.0.0`, so it's ready for most PaaS providers out of the box.

### Render / Railway (recommended, simplest)

1. Push this project to a GitHub repo.
2. Create a new **Web Service** on Render (or Railway) and point it at the
   repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app` (already declared in `Procfile`, so
   Render/Railway will pick it up automatically).
5. Deploy — the platform will set `PORT` for you automatically.

### Heroku

```
heroku create your-app-name
git push heroku main
```
Heroku also reads the `Procfile` automatically.

### Notes on the database in production

SQLite writes to a local file (`predictions.db`), which works fine for a
single small instance but **does not persist** on platforms with ephemeral
filesystems (e.g. Heroku's dynos reset on every deploy/restart) and won't
work correctly if you scale to multiple instances. For production use at
scale, swap `sqlite3` for a hosted database (e.g. Postgres) — the
`log_prediction` / `get_recent_predictions` functions in `app.py` are the
only places that would need to change.

## Notes on editing templates

- If you edit `templates/index.html` or `templates/history.html` in VS
  Code, turn off "Format On Save" for these files — auto-formatting can
  corrupt the `{% %}` Jinja tags.
- Don't rename the template files — Flask looks them up by their exact
  filenames (`index.html`, `history.html`).

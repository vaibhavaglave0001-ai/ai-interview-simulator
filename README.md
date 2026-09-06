# AI Interview Simulator

A beginner-friendly Flask, SQLite, Bootstrap, and Python NLP interview practice app.

## Install and run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000/` in a browser. The SQLite database is created and seeded from `data/interview_questions.csv` on first start. The first Sentence Transformers evaluation downloads `all-MiniLM-L6-v2`; if the model is unavailable, the evaluator uses the scikit-learn TF-IDF baseline automatically.

## Flow

Register or log in, select interview category/difficulty/question count, answer each question, and submit. Flask stores the session and answers in SQLite, evaluates each answer in Python, and renders the result dashboard with Jinja templates.

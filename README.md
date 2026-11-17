# AI Interview Simulator

A beginner-friendly Flask, SQLite, Bootstrap, and Python NLP interview practice app.

For Vercel architecture, hosted storage, migration, and deployment verification,
see [DEPLOYMENT.md](DEPLOYMENT.md). Production uses an ONNX export of the same
MiniLM model; the original local PyTorch backend remains available through
`requirements-local.txt`.

## Install and run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/prepare_model.py
$env:INTERVIEW_SCORING = 'onnx'
python app.py

```

Open `http://127.0.0.1:5000/` in a browser. The SQLite database is created and seeded from `data/interview_questions.csv` on first start. Existing databases receive additive schema updates automatically; users and answers are preserved.

Set a persistent, random `SECRET_KEY` environment variable before running multiple workers or deploying. Without it, a random development key is generated for each process, so restarting signs users out. Restart the app and reload existing browser pages after updating this version, since forms now include CSRF tokens and an interview identifier.

## Flow

Log in at `/login` to reach the home/dashboard at `/`. Click **Start an interview** to open **Set the room** at `/interview/setup`. Choose an interview type, difficulty, and 3, 5, or 10 questions, then click **Begin practice**. The existing `/interview/start` POST validates the settings, stores them with the interview in SQLite, and redirects to its first question. Answer submission advances through the session to the result dashboard.

Home and Set the Room reuse `templates/index.html` with `setup_mode`; they show distinct content without duplicate pages or a new routing library. Flask's existing routes and `url_for` handle navigation. Interview routes remain protected by authentication, and safe return URLs after sign-in are preserved. Missing/invalid settings or unavailable question pools return to setup with an error and do not replace an active interview. Login, setup, and answer forms show loading feedback, prevent repeated submissions, and reset when returning with the browser's Back button.

To check the navigation manually: log out, visit `/login`, log in, confirm Home shows **Start an interview** without the settings form, click it, choose **HR / Behavioral**, **Hard**, and **3 questions**, and click **Begin practice**. Confirm **Question 1 of 3**, **HR**, and **Hard**, then submit an answer and confirm **Question 2 of 3**. While logged out, opening `/interview/setup` or an interview-question URL must redirect to login.

## Scoring and response time

The cached `all-MiniLM-L6-v2` model loads and warms up once per process in a background thread. Requests never download models. While it loads, if the cache is missing, or if another request is using the model, answers receive immediate TF-IDF scoring. The result page identifies the method used; keyword and semantic similarity can produce different scores. Ideal-answer embeddings are cached, and CPU inference uses at most four threads.

To download the model once, before starting the server, run this command with network access:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-local.txt
.\.venv\Scripts\python.exe -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

Restart after installing a missing model. To use keyword scoring consistently and avoid loading the semantic model:

```powershell
$env:INTERVIEW_SCORING = "tfidf"
.\.venv\Scripts\python.exe app.py
```

Questions are selected from SQLite; there is no remote question-generation API. The legacy CSV is imported only when empty, and `data/question_bank.py` adds 405 curated questions idempotently to both new and existing databases. Each technical domain has 12 distinct concepts per difficulty; HR has 15 topics per difficulty. Choose Python, Java, C++, DSA, DBMS, Operating Systems, Computer Networks, AI, ML, or Web Development in setup. Older clients omitting a technical domain default to Python. HR ignores the domain field.

Selection filters repeated IDs and normalized wording, favors distinct topic keys, and samples without replacement. It prefers questions outside the user's latest comparable session, so the provided pools allow different sets between consecutive sessions. If too few unique valid questions remain, setup shows an error and preserves any current interview instead of padding the sequence. To extend the bank, add distinct topic/question/ideal-answer entries to `data/question_bank.py`; restart to import additions. Curated topic keys provide concept diversity; arbitrary paraphrases in manually added data cannot be reliably detected without assigning a shared topic key.

Each new session saves its ordered question IDs in `session_questions`, with unique constraints on both position and question ID. SQLite is authoritative even if an older cookie contains a different order. **Next Question** saves an answer and advances; **Previous Question** reviews a submitted answer, and its Next link returns through the same sequence. Submitted answers are read-only to preserve duplicate-submission safeguards. Unsaved text is retained per question in browser session storage when available. Questions are never regenerated during navigation. Valid unique interviews from before the update retain their sequence; legacy interviews containing repeated IDs ask the user to begin again. Existing completed results remain available.

SQLite uses WAL and indexed session/position lookups. Schema updates and seeding are serialized; enabling WAL has a bounded retry for concurrent startup. Scoring runs outside database connections; a unique position constraint prevents duplicate submissions from advancing an interview twice. The server records ended interviews and derives progress from persisted answers. Each response includes `Server-Timing: app;dur=...` in milliseconds, and requests taking at least one second are logged.

## Validation

Run from the project root:

```powershell
.\.venv\Scripts\python.exe -B tests_smoke.py
.\.venv\Scripts\python.exe -B -m unittest -v tests_project
node tests_frontend.cjs
.\.venv\Scripts\python.exe -B tests_runtime.py
```

The smoke and regression suites run offline with temporary databases. They cover all 18 category/difficulty/count combinations with actual fallback scoring, plus all 99 HR/domain/difficulty/count combinations for exact counts, unique IDs/text/concepts, domain isolation, saved answers and Previous/Next navigation. Additional checks cover duplicate pools, insufficient pools, session variation, persisted order, authentication, validation, CSRF, session replay, concurrent submissions, old tabs, result ownership, database migrations/integrity, model reuse/failures, and submission latency. The Node checks exercise domain selection, draft restoration, textarea resizing, saving feedback, duplicate protection, and Back navigation restoration using a simulated DOM.

The runtime check starts an actual local HTTP server with a disposable database, exercises registration through logout, and measures both startup fallback and real semantic scoring. It requires the semantic model to be cached and ready within 90 seconds. These checks do not verify browser layout, third-party Bootstrap/font delivery, or production network latency; perform a browser check on the deployed environment as well.

# Vercel deployment

The existing Flask app, Jinja templates, CSS, JavaScript, question bank, and
interview routes are retained. No external question-generation API is used.

## Production architecture

- Vercel runs `app.py` as one Flask function, using Python 3.12.
- The build downloads a pinned, full-precision ONNX export of the existing
  `sentence-transformers/all-MiniLM-L6-v2` model. Tokenization, masked mean
  pooling, normalization, cosine scoring, feedback thresholds, and TF-IDF
  fallback are preserved. No model download occurs during a request.
- Local SQLite remains supported. Vercel requires a TLS libSQL database
  (for example, a Turso database using the **libSQL engine**). Turso's newer
  engine needs a different driver; do not provision that engine for this app.
- Signed cookie sessions require one persistent secret across all instances.
  Database rows store interview progress and results. `/tmp` is not durable.

## Required Vercel environment variables

| Name | Value |
| --- | --- |
| `SECRET_KEY` | A cryptographically random value of at least 32 characters |
| `TURSO_DATABASE_URL` | TLS `libsql://...` connection URL |
| `TURSO_AUTH_TOKEN` | Database token; server only |
| `INTERVIEW_SCORING` | `onnx` |

Set these for Production and Preview separately. Prefer a separate database for
Preview. Never paste tokens into chat, source files, Git commits, or build logs.
Do not publish a deployment until its database and secret are configured.

## Database setup and existing data

`scripts/setup_database.py` reads credentials from the shell environment or the
ignored local `.env` file. It
backs up the existing `database.db` into a temporary snapshot, applies the
existing additive migrations to the snapshot, and copies schema and rows to an
**empty** remote database in one atomic batch. IDs, password hashes, questions,
answers, and relationships are preserved. The source database is not modified.
The script refuses a populated destination and checks row counts and foreign
keys afterward. Runtime connections also require foreign-key enforcement.

Run from the project root after securely setting the environment variables:

```powershell
.\.venv\Scripts\python.exe -B scripts/setup_database.py
```

For later schema changes, back up the hosted DB first and apply explicit additive
migrations. Runtime cold starts check the schema instead of recreating it.
Do not rerun initial setup against an existing destination.

## Local verification

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/prepare_model.py
$env:INTERVIEW_SCORING = 'onnx'
.\.venv\Scripts\python.exe -B -m unittest -v tests_deployment
.\.venv\Scripts\python.exe -B -m unittest -q tests_project
.\.venv\Scripts\python.exe -B tests_smoke.py
.\.venv\Scripts\python.exe -B tests_runtime.py
node tests_frontend.cjs
```

`tests_deployment.py` uses the real libSQL SDK's file transport to exercise the
adapter and migration without credentials. This does not validate a real hosted
connection. `tests_runtime.py` exercises real HTTP and semantic scoring with a
disposable database. For the original local PyTorch backend, install
`requirements-local.txt`, cache MiniLM as described in README, and use
`INTERVIEW_SCORING=semantic`.

## Deployment and live verification

Use `vercel.cmd login` on Windows for browser authorization, then link this
directory to the intended Vercel project. Configure the variables above, migrate
the database, and deploy a preview with `vercel.cmd`. Check build/runtime logs,
bundle size, templates/static routes, and a complete registration → login →
setup → questions → answer submission → results → logout flow. Confirm semantic
scoring was actually persisted and result ownership is enforced. Only then
publish production using `vercel.cmd --prod` and repeat the live flow.

The ignore files exclude local databases, credentials, virtual environments,
tests, and caches from upload. The build recreates `.model`; it is not committed.
Existing Git history may still contain previously tracked database data; deleting
a file from the index does not remove past commits.

## Verification status

Verified locally on 2026-11-17:

- All 40 existing regression tests passed after the application changes.
- All five deployment tests passed: real SDK adapter interview flows, rollback,
  snapshot migration/source preservation, ONNX inference, production cookie
  settings, and safe database-error responses.
- Smoke tests, frontend simulated-DOM checks, dependency checks, and
  `git diff --check` passed.
- A real local HTTP server completed registration, login, two interviews,
  answer evaluation, results, and logout. All six saved answers used semantic
  scoring. The second interview's median submit/next-page latency was 156 ms
  on this machine; this is not a production latency guarantee.
- Comparing six texts with the original cached PyTorch model and ONNX export
  produced a maximum pairwise cosine-score difference of 0.00000024.
- Linux/Python 3.12 wheel resolution succeeded. Uncompressed wheels plus model
  total about 455.7 MiB before deployment packaging; the actual Vercel build
  must still confirm the final bundle fits.

Vercel authorization is verified and the directory is linked to the separate
`ai-interview-simulator` project. The existing GitHub remote is accessible.
Vercel's automatic GitHub connection failed; CLI deployment remains available.

Pending: real hosted database provisioning/migration, Vercel build/deployment
logs, and live feature verification. Browser automation
was unavailable, so visual layout and browser console checks remain unverified.
No public deployment has been made yet.

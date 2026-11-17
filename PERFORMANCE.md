# Answer submission investigation

Measured locally on 2026-10-25 with the existing Python environment and cached
`all-MiniLM-L6-v2` model. Results vary with machine load and disk activity.

## Findings and changes

- Every answer previously constructed `SentenceTransformer` again. The first
  evaluation took 71.887 seconds and a second took 4.430 seconds, excluding the
  initial Python/scikit-learn import. Model construction could also contact
  Hugging Face and retry downloads inside a submission.
- The model now loads once per process, from local files, in a background thread.
  It is published only after warmup. Pending, unavailable, failed, or busy
  semantic inference uses immediate TF-IDF scoring. This avoids model-loading
  waits and inference queues, but the two scoring methods can produce different
  scores. Each answer stores its method, which is shown on the results page.
- Ideal-answer embeddings are cached in a bounded cache; CPU inference uses up
  to four threads. Direct real semantic evaluation measured 282.5 ms for a new
  ideal answer and 82.9 ms when its embedding was cached. Direct TF-IDF scoring
  measured 32.9 ms. These are scoring timings, not browser timings.
- Question selection used to reread CSV and look up every selected question by
  unindexed text. It now reads an indexed SQLite pool and keeps the question IDs.
  This also prevents CSV/database mismatches from crashing startup. There is no
  external question-generation service in this project.
- Scoring runs outside database connections. WAL permits readers during writes,
  and the session/position index supports progress and results queries. Progress
  comes from stored answers, with a unique answer per interview position.
- Replayed/concurrent submissions, submissions from an earlier interview tab,
  and replayed cookies after ending an interview are rejected safely. The UI
  displays saving feedback and prevents repeated clicks.
- Schema migrations and seed insertion are serialized in one write transaction
  so simultaneous startup workers cannot add the same column or seed twice.
- Empty TF-IDF vocabulary now returns zero instead of an exception. Answer
  lengths, missing questions, invalid form data, and redirects are handled.
  Forms have CSRF tokens; logout uses POST; the public hardcoded signing key was
  replaced with an environment key or a random development key.

## Measurements and checks

Real HTTP POST plus redirect and next-page HTML, using a temporary database:

| Mode | Median | Maximum |
| --- | ---: | ---: |
| During background startup, TF-IDF | 152.9 ms | 725.4 ms |
| Ready semantic model | 88.3 ms | 112.6 ms |

These are the final successful runtime-check samples. An earlier complete HTTP
flow measured medians of 51.8 ms for fallback and 189.1 ms for semantic scoring.

The runtime check exercised registration, login, two complete interviews,
results, and logout against an actual local HTTP server. It confirmed that
three answers used each scoring method and checked database integrity and
foreign keys. Background loading exceeded the test's 90-second readiness
deadline on one earlier run; subsequent runs became ready in roughly 6–25
seconds after starting HTTP requests. Submissions continued using fast fallback
while loading.

The offline regression suite covers all 18 category/difficulty/count
combinations with real fallback scoring, duplicate and parallel submissions,
authentication, CSRF, stale cookies/tabs, validation, result ownership, legacy
schema migration, indexes, and evaluator readiness/reuse/failure paths.
The original smoke test and simulated-DOM JavaScript checks are retained.
All tests use disposable databases and preserve the working database.

Final validation: all 28 regression tests passed, along with the original
3/5/10-question smoke test, JavaScript checks, and live HTTP runtime check.
`git diff --check` also passed.

`Server-Timing` records application request duration and requests over one
second are logged. Some requests during concurrent validation hit 1–3 seconds;
the subsecond measurements above are local samples, not latency guarantees.

## Verification limits

Browser automation exposed no available browser in this environment. Actual
layout, browser console/network errors, and third-party Bootstrap/Google Fonts
delivery remain unverified. HTTP and simulated-DOM tests do not measure browser
paint time or production network latency. No deployment was performed.

Restart the application and reload browser pages to apply these changes.
Set a persistent `SECRET_KEY` for deployment or multiple workers. See README
for test commands, model installation, and consistent TF-IDF mode.

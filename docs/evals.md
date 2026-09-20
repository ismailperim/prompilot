# Evaluating the agent

`backend/evals` is a set of 30 scripted requests — the kind people actually
type — run through the real agent loop against a real Prometheus and a real
model, with deterministic checks on what came out. It answers two questions:

- *Which model is good enough?* Same cases, different `--models`, one table.
- *Did this change make the agent worse?* Run it before and after touching
  the prompt, the tools or a provider.

It is not part of the test suite: it needs an LLM and costs tokens (roughly
100 model turns per model per run).

## Running it

Start the demo stack — the cases are written for it (node-exporter plus
Prometheus scraping itself) and use the notes in `knowledge/`:

```bash
docker compose up -d prometheus node-exporter
cd backend
uv run python -m evals                                   # model from .env
uv run python -m evals --models gpt-5-mini,qwen3-235b    # compare
uv run python -m evals --tags edit --verbose             # a subset, with details
uv run python -m evals --out report.json                 # machine-readable
```

LLM settings are the app's (`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`,
…); `--models` overrides `LLM_MODEL`. `--prometheus` and `--knowledge` point
elsewhere if your stack differs. The metric catalog is built once into
`backend/.evals/` and reused.

Output is one line per case — pass/fail, model turns, tool calls, seconds,
and the failed checks — plus a summary table when several models ran. The
exit code is non-zero if any case failed.

## What a case checks

Each case is a request plus an `Expect` (`evals/cases.py`): tools that must
or must not be called, how many panels came out and of which type and unit,
regexes the PromQL must match, whether every emitted query returns data
from Prometheus, what the answer must say and in which language, which
preloaded panels were patched or removed. A case passes only when every
check holds. Checks are deliberately loose about *how* — `rate` or `irate`,
`percent` or `percentunit` — and strict about *what*: the right metric, data
on the chart, the right panel touched.

Cases are tagged (`basic`, `cpu`, `disk`, `prometheus`, `question`, `lang`,
`edit`, …) so you can run a slice.

## Adding a case

Append a `Case` to `CASES`. Write the request the way a user would, keep
the expectation to what matters, and run it against at least two models —
if a strong model fails, the check is probably wrong, not the model.

## Results

Run on 2026-09-20 against the demo stack, through an OpenAI-compatible
gateway; `claude-sonnet-5` is the default model in development.

| Model | Passed | Avg model turns | Avg seconds |
| --- | --- | --- | --- |
| `claude-sonnet-5` | 30/30 | 3.7 | 9 |
| `gpt-5-mini` | 29/30 | 4.3 | 11 |
| `gemini-3.6-flash` | 27/30 | 5.0 | 10 |
| `qwen3-235b` | 25/30 | 4.4 | 5 |

What failed: `gemini-3.6-flash` and `qwen3-235b` spent the tool budget
re-running `search_catalog`/`query_prometheus` on filesystem and disk
requests without ever emitting a panel; `gpt-5-mini` and `qwen3-235b`
picked `MemFree` over `MemAvailable` although the notes say otherwise;
`qwen3-235b` also missed a `by (handler)` grouping and wrote a Turkish
CPU query that returned no data. Every model handled the edits to
existing panels and the plain questions. Small models are fine for the
basics; the gap shows on following the operator's notes and on knowing
when to stop exploring and emit.

# eval — golden set + Gemini LLM-as-judge (SPEC §13)

A minimal evaluation harness for the infra-ai MVP. It POSTs each golden case to the agent's
`/chat` endpoint **through Kong** (`localhost:8080`), collects the (SSE or JSON) answer, and
scores it with a **Gemini LLM-as-judge** on two of the five platform metrics:
**correctness** and **faithfulness**. Pass gate: **mean ≥ 0.8**.

## Files

| File | Purpose |
|---|---|
| `golden.jsonl` | ~8 cases incl. a **memory-recall** case (multi-turn, same `session_id`) and two **web-search** cases. |
| `run_eval.py` | stdlib-only runner: mint/read JWT → POST `/chat` → judge → mean → exit code. |
| `pyproject.toml` | metadata + ruff config (no runtime deps). |

## Run locally

```bash
# from infra-code/
cp .env.example .env && $EDITOR .env          # set GOOGLE_API_KEY + JWT_SECRET
make mvp-up-direct                            # cluster must be up + Kong /chat routed
make eval                                     # mints a JWT, runs run_eval.py
```

Or directly:

```bash
cd eval
export GOOGLE_API_KEY=...      # Gemini judge
export JWT_SECRET=...          # to auto-mint an HS256 token (or set JWT=<token> yourself)
export KONG_URL=http://localhost:8080
python3 run_eval.py
```

## Exit codes

- `0` — mean score ≥ 0.8 (**PASS**)
- `1` — mean score < 0.8 (**FAIL**)
- `2` — **graceful skip**: Kong/cluster unreachable, or no `GOOGLE_API_KEY`/JWT. CI treats
  this as non-fatal (the eval job needs no live cluster).

## Judge

Each case is scored by `gemini-2.5-flash` (override with `GEMINI_MODEL`) against the case's
`expected` answer and `rubric`. The per-case score is the mean of `correctness` and
`faithfulness`; the suite score is the mean across cases.

## Notes

- The **memory-recall** case sends two turns under one `session_id` and judges only the
  second answer — it must recall facts from the first turn via Graphiti session memory.
- The runner is **stdlib-only** (urllib/json/hmac) so it runs in CI with zero install.

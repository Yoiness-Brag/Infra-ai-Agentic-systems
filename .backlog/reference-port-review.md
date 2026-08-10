# Reference-port review — production-grade-agentic/

> **SCOPE NOTE (2026-06-02):** `production-grade-agentic/` is **only a reference agent-backend**, not
> platform code, and is **out of scope right now** (fully gitignored). It will be **modified later** to
> build the real agent and **deployed inside this infra-ai platform as a kagent K8s workload**. All
> items below are **deferred to Stage 07** (the port). Do **not** fix them now or build platform
> features from this code.

Full code review 2026-06-02. **Verdict: 58/100** — clean 7-layer skeleton and good LLM-resilience
patterns, but it does not boot as shipped and has real security/correctness defects. These are
addressed when the workload is ported in **Stage 07** (which also *removes* `mem0ai`, splits the
FastAPI monolith into `agent-orchestrator` + `agent-worker`, and lifts structlog/middleware/
telemetry/sanitization into `shared/py-common/`). Fix P0/P1 during the port, not before.

## CRITICAL (P0 — app will not import/boot)

### [REF-01] Broken import: `interface.api` does not exist
- **Status:** todo · **Stage:** 07 · **Refs:** `src/main.py:24`
- `from src.interface.api import api_router` → module is `src/interface/router.py`. Fix import.

### [REF-02] Broken import: agent tools
- **Status:** todo · **Stage:** 07 · **Refs:** `src/agent/tools/__init__.py:10`
- `from .duckduckgo_search import ...` → file is `web_search.py`. Fix import or rename.

### [REF-03] JWT secret not enforced; empty default
- **Status:** todo · **Stage:** 07 · **Refs:** `src/config/settings.py:162`
- `JWT_SECRET_KEY=os.getenv(...,"")` → HS256 signs with `""` ⇒ trivial forgery. Fail closed on empty;
  require min entropy.

### [REF-04] Hardcoded default DB password
- **Status:** todo · **Stage:** 07 · **Refs:** `src/config/settings.py:176`, `db_manager.py:69`
- `POSTGRES_PASSWORD="postgres"` default + prod path swallows DB init failure. No default; fail closed.

## HIGH (P1)

### [REF-05] Wildcard CORS with credentials
- `src/main.py:114-120` + `settings.py:143` default `["*"]` with `allow_credentials=True`. Require
  explicit origins in non-dev.

### [REF-06] `verify_token` is identity-agnostic
- `src/utils/auth.py:75`; `interface/auth.py:70,121`. User vs session tokens not distinguished. Add a
  `token_type`/`aud` claim and validate per dependency.

### [REF-07] Swallowed `None` → 200/contract break
- `src/agent/workflow.py:340-341` returns `None`; `interaction.py:63-67` builds `ChatResponse(None)`.
  Re-raise or return typed error.

### [REF-08] Fire-and-forget `asyncio.create_task` (memory updates)
- `workflow.py:334,393` — unreferenced tasks can be GC'd; failures vanish. Keep refs / task group /
  `add_done_callback`.

### [REF-09] Raw SQL table-name interpolation
- `workflow.py:445` f-string `DELETE FROM {table}`. Value parameterized, table not. Allowlist table names.

### [REF-10] DB init failure swallowed in prod; dual `DatabaseService` + eager `create_all` at import
- `db_manager.py:58,66,251` + `interface/auth.py:49`. Single shared instance via DI; move DDL to
  lifespan/migrations; fail fast on startup.

### [REF-11] Password HTML-escaping breaks login
- `interface/auth.py:68,173,214-215`. Registration hashes raw password; login sanitizes it ⇒ a
  password with `<>&"'` can register but never log in. Never HTML-escape secrets.

## MEDIUM / LOW (P2/P3)
- **P2:** sync SQLModel sessions inside `async def` block the loop (`db_manager.py` throughout);
  health endpoint type/status mismatch (`main.py:143,165`); `time.sleep` in async evaluator
  (`evals/evaluator.py:96,188`); rate-limit keyed on raw remote IP w/ no trusted-proxy
  (`system/rate_limit.py:14`); sanitization regex is dead/security-theater (`utils/sanitization.py:31`);
  `prepare_messages` mixes Message/dict types (`utils/graph.py:99-104`).
- **P3:** `print()` leaks user memory to stdout (`workflow.py:152`, `settings.py:59,74`); naive tz-less
  datetimes; `MAX_TOKENS` misused for reasoning models (`llm_provider.py`); orphaned `Thread` model;
  duplicated `validate_password_strength`; unused telemetry counters.

## Strengths to preserve in the port
Clean layering/SRP; tenacity retries + circular multi-model LLM fallback with loop guard
(`llm_provider.py`); request-scoped structured logging via ContextVar (`logs.py`); bcrypt + SecretStr;
connection-pool tuning; Prometheus + Langfuse instrumentation. → lift to `shared/py-common/`.

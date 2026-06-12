#!/usr/bin/env python3
"""Simple eval harness for the infra-ai MVP (SPEC §13).

Reads a JWT, POSTs each golden case to /chat through Kong (localhost:8080), collects the
streamed answer, and scores it with a Gemini LLM-as-judge on {correctness, faithfulness}
(2 of the 5 platform metrics). Prints the per-case + mean scores.

Exit codes:
  0  mean score >= PASS_GATE (0.8)
  1  mean score <  PASS_GATE
  2  graceful skip — cluster/Kong unreachable, no /chat to hit (CI tolerates this; see ci.yaml)

Env:
  JWT             Bearer token (mint with `make token`). If unset, the harness mints a
                  short-lived HS256 token from JWT_SECRET locally for convenience.
  JWT_SECRET      Used only if JWT is unset (local HS256 mint, iss=mvp-app).
  GOOGLE_API_KEY  Gemini key for the judge (required to score; otherwise skip with code 2).
  KONG_URL        Defaults to http://localhost:8080.
  GEMINI_MODEL    Judge model, defaults to gemini-2.5-flash.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, "golden.jsonl")

KONG_URL = os.environ.get("KONG_URL", "http://localhost:8080").rstrip("/")
CHAT_URL = f"{KONG_URL}/chat"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
PASS_GATE = 0.8
HTTP_TIMEOUT = 60
JWT_ISS = "mvp-app"

SKIP = 2


def _b64url(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def mint_token(secret: str) -> str:
    """Mint a short-lived HS256 JWT (iss=mvp-app) — mirrors `make token`."""
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    now = int(time.time())
    payload = _b64url(
        json.dumps(
            {"iss": JWT_ISS, "sub": "eval", "iat": now, "exp": now + 900},
            separators=(",", ":"),
        ).encode()
    )
    msg = header + b"." + payload
    sig = _b64url(hmac.new(secret.encode(), msg, hashlib.sha256).digest())
    return (msg + b"." + sig).decode()


def get_jwt() -> str | None:
    tok = os.environ.get("JWT")
    if tok:
        return tok
    secret = os.environ.get("JWT_SECRET")
    if secret:
        return mint_token(secret)
    return None


def load_golden() -> list[dict]:
    cases = []
    with open(GOLDEN, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def post_chat(token: str, session_id: str, message: str) -> str:
    """POST one message to /chat, returning the aggregated answer text.

    Tolerant of both plain-JSON and SSE (text/event-stream `data:` lines) responses.
    """
    body = json.dumps({"message": message, "session_id": session_id}).encode()
    req = urllib.request.Request(
        CHAT_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return _extract_answer(raw)


def _extract_answer(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    if "data:" in raw and "\n" in raw:
        chunks: list[str] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload in ("", "[DONE]"):
                continue
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                chunks.append(payload)
                continue
            for key in ("delta", "content", "text", "answer", "message", "response"):
                v = obj.get(key) if isinstance(obj, dict) else None
                if isinstance(v, str):
                    chunks.append(v)
                    break
        if chunks:
            return "".join(chunks).strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            for key in ("answer", "response", "content", "text", "message"):
                if isinstance(obj.get(key), str):
                    return obj[key].strip()
        return json.dumps(obj)
    except json.JSONDecodeError:
        return raw


def judge(api_key: str, question: str, expected: str, rubric: str, answer: str) -> dict:
    """Gemini LLM-as-judge: score correctness + faithfulness in [0,1]."""
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={api_key}"
    )
    prompt = (
        "You are a strict evaluation judge. Score the ASSISTANT ANSWER against the "
        "expected answer and rubric. Return ONLY a compact JSON object with two float "
        "fields in [0,1]: `correctness` (does the answer match the expected fact/result?) "
        "and `faithfulness` (is it grounded and non-fabricated relative to the rubric?). "
        "No prose, no markdown.\n\n"
        f"QUESTION: {question}\n"
        f"EXPECTED: {expected}\n"
        f"RUBRIC: {rubric}\n"
        f"ASSISTANT ANSWER: {answer}\n\n"
        'Respond exactly like: {"correctness": 0.0, "faithfulness": 0.0}'
    )
    req_body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
        }
    ).encode()
    req = urllib.request.Request(
        endpoint, data=req_body, method="POST", headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    scores = json.loads(text)
    c = float(scores.get("correctness", 0.0))
    f = float(scores.get("faithfulness", 0.0))
    return {"correctness": max(0.0, min(1.0, c)), "faithfulness": max(0.0, min(1.0, f))}


def main() -> int:
    token = get_jwt()
    if not token:
        print("SKIP: no JWT and no JWT_SECRET to mint one (set JWT or JWT_SECRET).", file=sys.stderr)  # noqa: E501
        return SKIP

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("SKIP: GOOGLE_API_KEY not set — cannot run the Gemini judge.", file=sys.stderr)
        return SKIP

    try:
        urllib.request.urlopen(
            urllib.request.Request(CHAT_URL, method="OPTIONS"), timeout=5
        )
    except urllib.error.HTTPError:
        pass
    except (urllib.error.URLError, OSError) as exc:
        print(f"SKIP: {CHAT_URL} unreachable ({exc}). Is the cluster up?", file=sys.stderr)
        return SKIP

    cases = load_golden()
    print(f"Running {len(cases)} golden cases against {CHAT_URL}\n")

    per_case: list[float] = []
    for case in cases:
        sid = case["session_id"]
        answer = ""
        try:
            for msg in case["messages"]:
                answer = post_chat(token, sid, msg)
        except (urllib.error.URLError, OSError, KeyError) as exc:
            print(f"[{case['id']:<22}] REQUEST ERROR: {exc}")
            per_case.append(0.0)
            continue

        try:
            s = judge(api_key, case["messages"][-1], case["expected"], case["rubric"], answer)
        except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
            print(f"[{case['id']:<22}] JUDGE ERROR: {exc}")
            per_case.append(0.0)
            continue

        case_score = (s["correctness"] + s["faithfulness"]) / 2.0
        per_case.append(case_score)
        print(
            f"[{case['id']:<22}] correctness={s['correctness']:.2f} "
            f"faithfulness={s['faithfulness']:.2f} -> {case_score:.2f}"
        )

    if not per_case:
        print("SKIP: no cases scored.", file=sys.stderr)
        return SKIP

    mean = sum(per_case) / len(per_case)
    print(f"\nMEAN SCORE: {mean:.3f}   GATE: {PASS_GATE}")
    if mean < PASS_GATE:
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# evals/metrics/

The five LLM-as-judge metric prompts, ported verbatim from the reference workload. Used by `eval-svc` for online scoring of every Langfuse trace.

```mermaid
flowchart LR
    LFW[Langfuse Web<br/>live trace] -->|read by cron every 60s| EVS[eval-svc]
    EVS -->|"5 prompts<br/>hallucination · helpfulness<br/>relevancy · conciseness · toxicity"| KONG[L1 Kong]
    KONG -->|judge model| LLM[Fast judge model<br/>Claude Haiku or local Ollama]
    LLM -->|structured score| EVS
    EVS -->|write back as Langfuse score| LFW
    EVS -->|"alert if 1h p50<br/>drops > 10%"| MIMIR[Mimir Ruler]
```

## Files

- `hallucination.md` — Does the response contain claims not grounded in retrieved context?
- `helpfulness.md` — Does the response answer what was asked?
- `relevancy.md` — Does the response stay on-topic?
- `conciseness.md` — Is the response appropriately scoped?
- `toxicity.md` — Does the response contain harmful, biased, or policy-violating content?

## Contract

Each file is a prompt template with two named placeholders: `{input}` and `{output}`. The judge LLM returns a JSON object with `score` (0.0–1.0) and `rationale` (free text). `eval-svc` parses the response and writes the score back to the Langfuse trace.

A PR that modifies a prompt requires an ADR — changing a prompt changes what "good" means.

## References

- Harness engineering doctrine: `docs/protocols/harness-engineering.md`.
- Reference workload mapping: `docs/reference/upstream-repo-mapping.md`.
- Stage 12 acceptance criteria: `docs/stages/STAGE-12-evaluation/README.md`.

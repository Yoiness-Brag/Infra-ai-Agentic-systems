# L7 — Evaluation services

```mermaid
flowchart LR
    EVS[eval-svc] -->|read traces| LFW[Langfuse v3]
    EVS -->|"5 LLM-as-judge prompts<br/>hallucination · helpfulness<br/>relevancy · conciseness · toxicity"| KONG[L1 Kong → judge model]
    EVS -->|write scores| LFW
    CI[GitHub Actions CI] -->|"trigger offline run"| EVS
    EVS -->|"DeepEval + Promptfoo<br/>+ Ragas + Inspect AI"| HARNESS[4-tool composition]
```

## Contents

| Service | Role |
|---|---|
| `eval-svc/` | Online LLM-as-judge scoring of live Langfuse traces (5 metrics) + offline orchestration of the 4-tool CI harness composition. |

## References

- Layer specification: `docs/layers/L7-observability-reliability/README.md`.
- Harness engineering doctrine: `docs/protocols/harness-engineering.md`.
- Five-metric prompts ported from: `docs/reference/upstream-repo-mapping.md`.

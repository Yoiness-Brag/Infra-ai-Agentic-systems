# evals/

The platform's evaluation artifacts: golden datasets, DeepEval suites, Promptfoo configs, Ragas suites, Inspect AI suites, and the five LLM-as-judge metric prompts. These artifacts are consumed by `eval-svc` (online scoring) and CI (offline gating).

```mermaid
flowchart TB
    EVALS[evals/]
    EVALS --> DATA[datasets/<br/>golden JSONL]
    EVALS --> DEEP[deepeval-suites/<br/>pytest-style app evals]
    EVALS --> PROMPTFOO[promptfoo/<br/>YAML prompt matrices + red-team]
    EVALS --> RAGAS[ragas-suites/<br/>RAG quality]
    EVALS --> INSPECT[inspect-suites/<br/>UK AISI safety + capability]
    EVALS --> METRICS[metrics/<br/>5 LLM-as-judge prompts]

    DATA -.->|fed into| DEEP
    DATA -.->|fed into| RAGAS
    DATA -.->|fed into| INSPECT

    DEEP --> EVS[eval-svc<br/>CI runner]
    PROMPTFOO --> EVS
    RAGAS --> EVS
    INSPECT --> EVS
    METRICS --> EVS_ONLINE[eval-svc<br/>online scorer]
```

## Why a four-tool composition

No single evaluation tool covers all four layers (application unit, prompt matrix + red-team, RAG-specific, safety + capability). The doctrine `docs/protocols/harness-engineering.md` explains the choice in detail.

## References

- Harness engineering doctrine: `docs/protocols/harness-engineering.md`.
- Testing strategy doctrine: `docs/protocols/testing-strategy.md`.
- DeepEval: https://github.com/confident-ai/deepeval
- Promptfoo: https://www.promptfoo.dev/
- Ragas: https://docs.ragas.io/
- Inspect AI (UK AISI): https://inspect.ai-safety-institute.org.uk/

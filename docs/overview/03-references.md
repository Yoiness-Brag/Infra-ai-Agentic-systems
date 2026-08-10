# References

Every architectural decision in this repository is backed by a validated source. This document indexes them so any reader can verify our claims independently. Entries are grouped by topic and dated to the validation moment.

## Seven-layer model

- Fareed Khan, "Building the 7 Layers of a Production-Grade Agentic AI System," Level Up Coding (Medium), December 2025. https://levelup.gitconnected.com/building-the-7-layers-of-a-production-grade-agentic-ai-system-37ee5d941f1c
- JIN, "The 7 Layers of a Production-Grade Agentic AI System: An Architect's Deep Dive," AImonks (Medium), December 22, 2025. https://medium.com/aimonks/the-7-layers-of-a-production-grade-agentic-ai-system-an-architects-deep-dive-b00e78459fe6
- Asimsultan, "7 Layers of a Production-Grade Agentic AI System," Medium, January 2026. https://medium.com/@asimsultan2/7-layers-of-a-production-grade-agentic-ai-system-8515122924cf
- Reference repository: FareedKhan-dev/production-grade-agentic-system on GitHub. https://github.com/FareedKhan-dev/production-grade-agentic-system

## kagent (base platform)

- kagent project site. https://kagent.dev
- kagent GitHub: kagent-dev/kagent. https://github.com/kagent-dev/kagent
- CNCF project page: kagent accepted into Sandbox May 22, 2025. https://www.cncf.io/projects/kagent/
- Solo.io announcement of CNCF contribution at KubeCon Europe 2025. https://www.solo.io/blog/bringing-agentic-ai-to-kubernetes-contributing-kagent-to-cncf

## A2A protocol

- A2A protocol homepage. https://a2a-protocol.org
- Linux Foundation press release (June 23, 2025): https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents
- Adoption milestones (April 2026, 150+ organizations): https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year
- IBM ACP / BeeAI merger note: https://a2ac.io/projects/acp-beeai

## MCP

- Model Context Protocol, Linux Foundation. (Donated by Anthropic, hosted under the Agentic AI Foundation.)
- Kong AI Gateway MCP integration docs: https://developer.konghq.com/ai-gateway/

## Kong AI Gateway

- Kong AI Gateway product page. https://konghq.com/products/kong-ai-gateway
- Kong AI Gateway developer docs. https://developer.konghq.com/ai-gateway/
- Kong AI Connectivity 2026 roadmap announcement (March 11, 2026): https://techbytes.app/posts/kong-ai-connectivity-agentic-stack-governance/
- Kong Gateway changelog (semantic routing, circuit breaker, Bedrock batch API, etc.): https://developer.konghq.com/gateway/changelog/

## CubeSandbox

- TencentCloud/CubeSandbox GitHub repository. https://github.com/TencentCloud/CubeSandbox
- Architecture overview document. https://github.com/TencentCloud/CubeSandbox/blob/master/docs/architecture/overview.md
- "Cube Sandbox" review on aitoolnet (April 23, 2026). https://www.aitoolnet.com/cube-sandbox
- Tencent Cloud open-sources Cube Sandbox: https://en.theblockbeats.news/flash/342311
- Comparison piece (CubeSandbox vs E2B, April 2026, Apache 2.0 license confirmation). https://wavespeed.ai/blog/pt/posts/cubesandbox-vs-e2b/

## Graphiti and FalkorDB

- Zep Graphiti open source. https://www.getzep.com/product/open-source/
- Graphiti paper (arXiv 2501.13956). https://arxiv.org/abs/2501.13956
- Neo4j developer blog on Graphiti (FalkorDB, Kuzu also supported): https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/
- Codex Blog assessment (March 2026): https://codex.danielvaughan.com/2026/03/30/graphiti-agent-memory-store/

## Memory comparison (Mem0 vs Zep/Graphiti vs others)

- Yogesh Yadav, "AI Agent Memory Systems in 2026," Dev Genius (March 2026). https://blog.devgenius.io/ai-agent-memory-systems-in-2026-mem0-zep-hindsight-memvid-and-everything-in-between-compared-96e35b818da8

## Anthropic orchestrator-worker pattern

- Anthropic engineering blog: "How we built our multi-agent research system" (June 2025).
- ZenML LLMOps Database case studies: https://www.zenml.io/llmops-database/building-production-multi-agent-research-systems-with-claude
- ByteByteGo summary: https://blog.bytebytego.com/p/how-anthropic-built-a-multi-agent
- The Sequence Engineering #671 paid analysis. https://thesequence.substack.com/p/the-sequence-engineering-671-how

## OpenTelemetry GenAI semantic conventions

- OpenTelemetry blog: "Inside the LLM Call — GenAI Observability with OpenTelemetry" (May 14, 2026). https://opentelemetry.io/blog/2026/genai-observability/
- Uptrace: "OpenTelemetry for AI Systems" (April 2026). https://uptrace.dev/blog/opentelemetry-ai-systems
- Datadog native GenAI semconv support (December 2025). https://www.datadoghq.com/blog/llm-otel-semantic-convention/
- PII redaction guidance, maketocreate.com (May 2026). https://maketocreate.com/opentelemetry-genai-tracing-ai-agents-without-leaking-pii/

## Langfuse self-hosted

- Langfuse self-hosting docs. https://langfuse.com/self-hosting
- Helm chart guide. https://langfuse.com/self-hosting/deployment/kubernetes-helm
- ClickHouse on Kubernetes (Bitnami chart) guidance. https://langfuse.com/self-hosting/infrastructure/clickhouse
- langfuse/langfuse-k8s Helm chart repository. https://github.com/langfuse/langfuse-k8s

## Grafana AI Observability and LGTM stack

- Grafana AI Observability docs. https://grafana.com/docs/grafana-cloud/machine-learning/ai-observability/
- "How to monitor LLMs in production with Grafana Cloud, OpenLIT, and OpenTelemetry." https://grafana.com/blog/ai-observability-llms-in-production/
- OpenLIT Operator zero-code Kubernetes instrumentation. https://grafana.com/blog/ai-observability-zero-code/
- OneUptime LGTM stack guide (February 2026). https://oneuptime.com/blog/post/2026-02-06-lgtm-stack-opentelemetry/view

## NATS JetStream and event-driven patterns

- "Real-Time Event Streaming: Kafka vs Redis Streams vs NATS in 2026," DEV Community (March 2026). https://dev.to/young_gao/real-time-event-streaming-kafka-vs-redis-streams-vs-nats-in-2026-34o1
- Encore Cloud, "Event-Driven Architecture in 2026" (May 2026). https://encore.cloud/resources/event-driven-architecture

## K3s and ArgoCD

- K3s CNCF project page. https://www.cncf.io/projects/k3s/
- K3s Helm controller docs. https://docs.k3s.io/add-ons/helm
- ArgoCD on K3s guide (February 2026). https://oneuptime.com/blog/post/2026-02-26-install-argocd-k3s/view
- GitOps best practices for 2026. https://devopstales.com/tools-and-technologies/gitops-best-practices-2026/
- ArgoCD Image Updater docs. https://argocd-image-updater.readthedocs.io/en/stable/basics/update-methods/
- ArgoCD + GitHub Actions integration guide (February 2026). https://oneuptime.com/blog/post/2026-02-26-argocd-github-actions-integration/view
- Hypatos: Optimizing ArgoCD for monorepo setup. https://medium.com/@michail.gebka/optimizing-argocd-for-monorepo-setup-7c5f548e5575

## Microsoft Agent Framework (compared, not adopted)

- Microsoft Foundry blog (October 2025). https://devblogs.microsoft.com/foundry/introducing-microsoft-agent-framework-the-open-source-engine-for-agentic-ai-apps/

## Qdrant

- Qdrant 2025 Recap. https://qdrant.tech/blog/2025-recap/
- Qdrant AI agents page. https://qdrant.tech/ai-agents/

## Sandbox comparison

- Fastio, "10 Best Code Execution Sandboxes for AI Agents" (February 2026). https://fast.io/resources/best-code-execution-sandboxes-ai-agents/
- Northflank, "Daytona vs E2B in 2026" (February 2026). https://northflank.com/blog/daytona-vs-e2b-ai-code-execution-sandboxes
- Spheron blog, AI agent sandbox setup guide (March 2026). https://www.spheron.network/blog/ai-agent-code-execution-sandbox-e2b-daytona-firecracker/

## Grafana Alloy and Pyroscope

- Grafana Alloy product page: https://grafana.com/oss/alloy-opentelemetry-collector/
- Alloy v1.0 release announcement (Grafana Labs): https://grafana.com/blog/2024/04/09/grafana-alloy-opentelemetry-collector-with-prometheus-pipelines/
- Alloy v1.0 release on GitHub: https://github.com/grafana/alloy/releases/tag/v1.0.0
- Alloy GitHub repository: https://github.com/grafana/alloy
- "How to Compare OpenTelemetry Collector vs Grafana Alloy" (February 2026): https://oneuptime.com/blog/post/2026-02-06-compare-opentelemetry-collector-vs-grafana-alloy/view
- "How to Use Grafana Alloy as an OpenTelemetry Collector Alternative" (February 2026): https://oneuptime.com/blog/post/2026-02-06-grafana-alloy-opentelemetry-collector-alternative/view
- Coralogix critique of Alloy soft lock-in (the negative-consequences source for ADR-0006): https://coralogix.com/blog/the-grafana-alloy-dilemma/
- "From Agent to Alloy: Why we transitioned to the Alloy collector and why you should, too" (Grafana Labs): https://grafana.com/blog/grafana-agent-to-grafana-alloy-opentelemetry-collector-faq/

## kagent architecture and HA

- kagent architecture documentation (Python ADK ~15s startup vs Go ADK ~2s; controller, engine, UI, CLI): https://kagent.dev/docs/kagent/concepts/architecture
- DeepWiki overview of kagent: https://deepwiki.com/kagent-dev/kagent
- kagent project site: https://kagent.dev
- kagent GitHub: https://github.com/kagent-dev/kagent
- CNCF Sandbox project page (accepted May 22, 2025): https://www.cncf.io/projects/kagent/
- Solo.io CNCF contribution announcement: https://www.solo.io/blog/bringing-agentic-ai-to-kubernetes-contributing-kagent-to-cncf

## Context engineering

- Atlan, "What Is Context Engineering? Complete 2026 Guide": https://atlan.com/know/what-is-context-engineering/
- deepset, "Context Engineering: The Next Frontier Beyond Prompt Engineering": https://www.deepset.ai/blog/context-engineering-the-next-frontier-beyond-prompt-engineering
- Damon McMillan, "Structured Context Engineering for File-Native Agentic Systems" (peer-reviewed, February 2026, 9,649 experiments; validates that format choice (YAML/JSON/MD/TOON) is statistically insignificant; structure and selection matter).
- DEV Community, "Context Engineering: Why It's Replacing Prompt Engineering in 2026": https://dev.to/serenitiesai/context-engineering-why-its-replacing-prompt-engineering-in-2026-1b4g
- Machine Learning Mastery, "Effective Context Engineering for AI Agents: A Developer's Guide": https://machinelearningmastery.com/effective-context-engineering-for-ai-agents-a-developers-guide/
- QubitTool, "Complete Guide to Context Engineering: The Evolution from Prompt Engineering": https://qubittool.com/blog/context-engineering-complete-guide
- Neo4j, "Why AI Teams Are Moving From Prompt Engineering to Context Engineering" (January 2026): https://neo4j.com/blog/agentic-ai/context-engineering-vs-prompt-engineering/
- Meta Intelligence, "Context Engineering Guide: RAG, Memory Systems & Dynamic Context for Production AI [2026]" (lost-in-the-middle attention blind spot, ~30% information loss prevention): https://www.meta-intelligence.tech/en/insight-context-engineering

## Harness engineering (4-tool composition)

- Pinggy, "AI Harness Engineering: The Layer That Makes Your LLM Applications Actually Work" (May 2026): https://pinggy.io/blog/best_ai_harnesses_to_supercharge_llm_models/
- Intuz / Towards Data Science, "Building an Evaluation Harness for Production AI Agents: A 12-Metric Framework From 100+ Deployments" (2-3 weeks setup time data point; May 2026): https://towardsdatascience.com/building-an-evaluation-harness-for-production-ai-agents-a-12-metric-framework-from-100-deployments/
- Inference.net, "LLM Evaluation Tools: The Complete Comparison Guide (2026)": https://inference.net/content/llm-evaluation-tools-comparison/
- DevopsSchool, "Top 10 LLM Evaluation Harnesses: Features, Pros, Cons & Comparison": https://www.devopsschool.com/blog/top-10-llm-evaluation-harnesses-features-pros-cons-comparison/
- Best AI Web, "How to Benchmark LLMs with lm-evaluation-harness, HELM, and OpenCompass in 2026": https://www.bestaiweb.ai/how-to-benchmark-llms-with-lm-evaluation-harness-helm-and-opencompass-in-2026/
- Best AI Web, "What Is an Evaluation Harness? How LLM Benchmarks Work": https://www.bestaiweb.ai/what-is-an-evaluation-harness-and-how-standardized-frameworks-benchmark-llms/
- Stanford CRFM HELM, EleutherAI lm-evaluation-harness, UK AISI Inspect AI source projects.
- DeepEval (Confident AI), Promptfoo, Ragas documentation.

## RAG architecture and hybrid search

- DEV Community / Pooyagolchian, "RAG Pipelines in Production: Vector Database Benchmarks, Chunking Strategies, and Hybrid Search Data" (April 2026): https://dev.to/pooyagolchian/rag-pipelines-in-production-vector-database-benchmarks-chunking-strategies-and-hybrid-search-data-gbl
- MyEngineeringPath, "Advanced RAG — Hybrid Search, Reranking & Knowledge Graphs (2026)" (alpha=0.75 starting point for weighted fusion; March 2026): https://myengineeringpath.dev/genai-engineer/advanced-rag/
- Lushbinary, "RAG Production Guide 2026" (40% retrieval failure rate on naive RAG; RAGAS thresholds; agentic RAG cost analysis): https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide/
- Suhas Mallesh, "Azure AI Search Advanced RAG with Terraform: Hybrid Search, Semantic Ranking, and Agentic Retrieval" (March 2026; agentic-retrieval pattern): https://medium.com/@suhasmallesh/azure-ai-search-advanced-rag-with-terraform-hybrid-search-semantic-ranking-and-agentic-retrieval-fb141ad34c7d
- Beltsys Labs, "What Is RAG? Complete Guide to Retrieval-Augmented Generation in 2026": https://beltsys.com/en/blog/what-is-rag-complete-guide/
- Pavan Kumar, "Mastering Chunking for Effective RAG: Beyond Basics with Qdrant and Reranking": https://medium.com/towardsdev/mastering-chunking-for-effective-rag-beyond-basics-with-qdrant-and-reranking-bb0761ae84e4
- ragaboutit.com, "How to Build a Production-Ready RAG System with Qdrant's New Hybrid Search": https://ragaboutit.com/how-to-build-a-production-ready-rag-system-with-qdrants-new-hybrid-search-the-complete-vector-database-implementation-guide/

## Testing strategy for agentic systems

- Sitepoint, "AI Agent Testing Automation: Developer Workflows for 2026" (mock-LLM-via-DI, fixture-based eval, threshold-based CI gates): https://www.sitepoint.com/ai-agent-testing-automation-developer-workflows-for-2026/
- CloudQA, "2026 Software Testing Trends: The Shift from Scripted to Agentic AI" (contract testing reduces environment complexity by 80%; chaos engineering standard practice): https://cloudqa.io/2026-software-testing-trends-the-shift-from-scripted-to-agentic-ai/
- vtestcorp, "Agentic Testing: The Complete Guide to AI-Powered Software Testing in 2026": https://vtestcorp.com/insights/agentic-testing-the-complete-guide-to-ai-powered-software-testing-in-2026/
- Industry references for testcontainers-python, locust, toxiproxy, schemathesis, freezegun, mutmut.

# Clinical LLMOps Platform — Project Roadmap

---

### Foundation — Kubernetes & Infrastructure (Phases 1–7)

| Phase | Focus | Status | Key Deliverables |
|-------|-------|--------|------------------|
| 1 | K8s Foundation | ✅ Complete | Pods, Deployments, Services, Labels |
| 2 | Configuration | ✅ Complete | ConfigMaps, Secrets, Kustomize |
| 3 | Persistence | ✅ Complete | PVCs, StatefulSets, Headless Services |
| 4 | Observability | ✅ Complete | Probes (startup/liveness/readiness), Resource Limits |
| 5 | Deployment Strategies | ✅ Complete | Rolling Updates, Rollbacks, Blue-Green |
| 6 | Scaling | ✅ Complete | HPA, Metrics Server, Load Testing |
| 7 | Ingress & Security | ✅ Complete | Ingress, NetworkPolicies, RBAC |

---

### LLM Gateway — Routing & Guardrails (Phases 8–11)

| Phase | Focus | Status | Key Deliverables |
|-------|-------|--------|------------------|
| 8 | Provider Routing | ✅ Complete | Modular provider architecture, config-driven model routing |
| 9 | Router Enhancements | ✅ Complete | `rank_providers()` with private flag, cost-based ranking, fallback chains |
| 10 | Guardrails Phase 1 | ✅ Complete | Content safety guard — 12 threat categories, keyword scan |
| 11a | Guardrails Phase 2a | ✅ Complete | PII Guard — 6 types, 3 masking strategies, 27 tests |
| 11b | Guardrails Phase 2b | ✅ Complete | Jailbreak Guard — 3 detection layers, confidence scoring, 16 tests |
| — | OpenAI Provider | ✅ Complete | Live-tested with real API calls, prefix routing fix |

---

### Cloud Deployment (Phases 12–14)

| Phase | Focus | Status | Key Deliverables |
|-------|-------|--------|------------------|
| 12 | EKS Deployment | 🔧 In Progress | ECR repo + image pushed, eksctl cluster config, prod overlay. Remaining: deploy app, secrets, test, Ollama PVC for EBS |
| 13 | ArgoCD GitOps | ⬜ Deferred | Declarative application delivery — revisit after 13i |
| 14 | Terraform IaC | ⬜ Deferred | Infrastructure as Code — revisit after 13i |

---

### Ambient Clinical Documentation Ops Platform (Phase 13a–13i)

*Reframes the gateway into a vertical LLMOps platform for ambient clinical documentation. All infrastructure from Phases 1–12 becomes the foundation.*

**Dependency order:** 13a → (13b, 13c parallel) → 13d → (13e, 13f parallel) → 13g → 13h → 13i

| Phase | Focus | Status | Key Deliverables | Double-Dip |
|-------|-------|--------|------------------|------------|
| 13a | Encounter Domain Model | ⬜ Planned | Postgres DDL: encounters, transcripts, generated_notes, note_versions, attestations, audit_events, tool_calls. Encounter-scoped audit trail. Synthetic golden set (~50 transcripts, 5 specialties via Claude) | — |
| 13b | PHI Guard + Compliance Routing | ⬜ Planned | Extend PII Guard → HIPAA Safe Harbor 18 identifiers. Policy engine: `contains_phi=true` → Bedrock/local only. Vektor-Guard as input guardrail | Vektor-Guard |
| 13c | Clinical Reasoning Agent | ⬜ Planned | LangGraph agent replaces thin pipeline. Analyzes transcript, decides which MCP tools to call (meds, labs, prior notes, ICD-10, NPI, allergies), gathers context, generates structured SOAP/DAP/BIRP note. Vela Healthcare MCP as bidirectional tool server. Tool calls persisted alongside notes | Vela MCP, LangGraph |
| 13d | MLflow Registry + Version Fingerprinting | ⬜ Planned | Prompts, guardrail configs, routing policies, agent graph config as versioned MLflow artifacts. `version_fingerprint = hash(prompt, guardrail, routing, provider, model, revision, tools_invoked)` — reconstruct exact inference config and agent reasoning path for any encounter | Adversarial AI Ch18 |
| 13e | Clinical Eval Module + CI Gate | ⬜ Planned | Purpose-built scoring engine (internal). Dimensions: factual faithfulness (LLM judge), PHI leakage (deterministic), clinical completeness (LLM judge), format compliance (deterministic), tool selection quality (did the agent call the right MCP tools?), length distribution. CI gate: >2% regression auto-fails PR | — |
| 13f | Attestation Telemetry | ⬜ Planned | Lifecycle tracking: generated → delivered → viewed → edited → signed. Webhook endpoints receive lifecycle events from Vela MCP. Key metric: `signed_without_view_rate`. Secondary: `median_time_to_review`, `edit_distance_distribution` | — |
| 13g | Drift Detection Service | ⬜ Planned | Prometheus recording rules: 14-day rolling baselines for hallucination rate, refusal rate, note length P50/P95, guardrail trigger rate, attestation compliance, tool selection accuracy — segmented by specialty and provider model. Alertmanager fires at >2σ deviation | — |
| 13h | Observability Stack + Dashboards | ⬜ Planned | Prometheus + Grafana + OpenTelemetry. Four dashboards (JSON committed): Clinical Quality, Attestation Compliance, Unit Economics, Inference Health. Agent trace visualization showing tool call decisions | — |
| 13i | EKS Redeploy + End-to-End Demo | ⬜ Planned | Recreate cluster, push v22+ images including MLflow, Prometheus, Grafana, attestation webhook receiver. Full agent demo: transcript in → tool calls → note out → eval scored → attestation tracked. Record for Inference Loop + interview | — |

---

### Security Assessment (Phases 15–18)

*Uses the project's own infrastructure as the scan target for practical security assessment.*

| Phase | Focus | Status | Key Deliverables |
|-------|-------|--------|------------------|
| 15 | Local Security Baseline | ⬜ Planned | kind cluster (1 control + 2 workers), kube-bench CIS scan, kube-hunter passive/active, Python parsers, SQLite result storage |
| 16 | EKS Security Audit | ⬜ Planned | kube-bench EKS profile, kube-hunter remote mode, findings on: llm-api-keys Secret, etcd encryption, ServiceAccount tokens, Redis NetworkPolicy, Ingress TLS. Delta vs kind baseline |
| 17 | Intentional Misconfiguration Lab | ⬜ Planned | Dedicated kind cluster, 6 deliberate misconfigs, detect each with kube-bench/kube-hunter, cumulative attack surface report |
| 18 | Remediation and Hardening | ⬜ Planned | Fix all findings into main manifests, CIS control references in commit messages, before/after CIS scores, README "Security Posture" section |

---

### Remaining Provider Work

| Item | Status | Notes |
|------|--------|-------|
| Anthropic Provider | ⬜ Planned | Build after EKS, same pattern as OpenAI |
| AWS Bedrock Provider | ⬜ Planned | Required for 13b compliance routing (PHI → Bedrock only) |

---

### Interview-Ready Minimum Cut

If a Principal Architect interview comes up in the next 6 weeks:

**13a + 13b + 13c + 13e (synthetic golden set) + 13f + Attestation Compliance dashboard**

This gives you: encounter data model, PHI-aware routing, a working clinical reasoning agent with MCP tool calls, eval module scoring both note quality and tool selection, attestation telemetry (the differentiator), and a dashboard to show it all.

---

### Timeline Estimate

| Block | Phases | Est. Duration |
|-------|--------|---------------|
| EKS deployment wrap-up | 12 | 1 session |
| Clinical ops platform | 13a–13i | 10–14 weeks @ 6–8 hrs/week |
| Security assessment | 15–18 | 4–6 weeks @ 6–8 hrs/week |

**Double-dip rule:** 13c = LangGraph + Vela MCP, 13d = Adversarial AI Ch18, 13b = Vektor-Guard integration. No standalone sessions — book everything against existing threads so deliverables compound.

---

*Current image: ai-gateway:v21 | Current deploy target: minikube (local) + EKS us-west-2 (cloud)*

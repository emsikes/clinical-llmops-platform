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

### Cloud Deployment (Phases 12, 15–16)

| Phase | Focus | Status | Key Deliverables |
|-------|-------|--------|------------------|
| 12 | EKS Deployment | 🔧 In Progress | ECR repo + image pushed, eksctl cluster config, prod overlay. Remaining: deploy app, secrets, test, Ollama PVC for EBS |
| 15 | ArgoCD GitOps | ⬜ Deferred | Declarative application delivery — revisit after 13i |
| 16 | Terraform IaC | ⬜ Deferred | Infrastructure as Code — revisit after 13i |

> **Note:** ArgoCD and Terraform renumbered from 13/14 to 15/16 to free Phase 14
> for the vLLM serving refactor. GPU nodegroup provisioning for EKS lands in
> Phase 14; if Phase 14 sequences before the final EKS deploy, provision GPU
> nodes (g5/g6) during Phase 12 instead.

---

### Ambient Clinical Documentation Ops Platform (Phase 13a–13i)

*Reframes the gateway into a vertical LLMOps platform for ambient clinical documentation. All infrastructure from Phases 1–12 becomes the foundation.*

**Dependency order:** 13a → (13b, 13c parallel) → 13d → (13e, 13f parallel) → 13g → 13h → 13i

| Phase | Focus | Status | Key Deliverables | Double-Dip |
|-------|-------|--------|------------------|------------|
| 13a | Encounter Domain Model | ✅ Complete | Postgres DDL: encounters, transcripts, generated_notes, tool_calls, attestations, audit_events (6 tables + 7 indexes). SQLAlchemy 2.0 async models, database.py, FastAPI lifespan, POST /v1/encounters live-tested. Alembic baselined. Golden set: 5 synthetic transcripts (card/pc/ortho/psych/em). Schema ERD generated | — |
| 13b | PHI Guard + Compliance Routing | 🔧 In Progress | Extend PII Guard → HIPAA Safe Harbor 18 identifiers (6 PII copied + 12 new). 3-tuple pattern shape with phi_category tag. `contains_phi=true` → BAA-covered only (Bedrock, Ollama; vLLM added Phase 14). PHI Guard on /v1/clinical/notes; PII Guard stays on /v1/chat/completions. Vektor-Guard as input guardrail | Vektor-Guard |
| 13c | Clinical Reasoning Agent | ⬜ Planned | LangGraph agent replaces thin pipeline. Analyzes transcript, decides which MCP tools to call (meds, labs, prior notes, ICD-10, NPI, allergies), gathers context, generates structured SOAP/DAP/BIRP note. Vela Healthcare MCP as bidirectional tool server. Tool calls persisted alongside notes | Vela MCP, LangGraph |
| 13d | MLflow Registry + Version Fingerprinting | ⬜ Planned | Prompts, guardrail configs, routing policies, agent graph config as versioned MLflow artifacts. `version_fingerprint = hash(prompt, guardrail, routing, provider, model, revision, tools_invoked)` — reconstruct exact inference config and agent reasoning path for any encounter | Adversarial AI Ch18 |
| 13e | Clinical Eval Module + CI Gate | ⬜ Planned | Purpose-built scoring engine (internal). Dimensions: factual faithfulness (LLM judge), PHI leakage (deterministic), clinical completeness (LLM judge), format compliance (deterministic), tool selection quality (did the agent call the right MCP tools?), length distribution. CI gate: >2% regression auto-fails PR | — |
| 13f | Attestation Telemetry | ⬜ Planned | Lifecycle tracking: generated → delivered → viewed → edited → signed. Webhook endpoints receive lifecycle events from Vela MCP. Key metric: `signed_without_view_rate`. Secondary: `median_time_to_review`, `edit_distance_distribution`. Groups by ThreatCategory (PHI/PII) + phi_category Safe Harbor tags for audit | — |
| 13g | Drift Detection Service | ⬜ Planned | Prometheus recording rules: 14-day rolling baselines for hallucination rate, refusal rate, note length P50/P95, guardrail trigger rate, attestation compliance, tool selection accuracy — segmented by specialty and provider model. Alertmanager fires at >2σ deviation | — |
| 13h | Observability Stack + Dashboards | ⬜ Planned | Prometheus + Grafana + OpenTelemetry. Four dashboards (JSON committed): Clinical Quality, Attestation Compliance, Unit Economics, Inference Health. Agent trace visualization showing tool call decisions | — |
| 13i | EKS Redeploy + End-to-End Demo | ⬜ Planned | Recreate cluster, push v22+ images including MLflow, Prometheus, Grafana, attestation webhook receiver. Full agent demo: transcript in → tool calls → note out → eval scored → attestation tracked. Record for Inference Loop + interview | — |

#### Phase 13b — Session Decisions (locked)

- 6 PII patterns **copied** into PHI_PATTERNS (independent, not imported) for decoupled evolution
- Entry shape: 3-tuple `Dict[str, Tuple[re.Pattern, Severity, str]]`, 3rd element = phi_category Safe Harbor tag
- Safe Harbor #17 (photographs) out of scope (text-only); #18 (catch-all) via keyword detection
- **Enum fix:** added `PII = "pii"` and `PHI = "phi"` to `ThreatCategory` (+ guardrails-settings.yaml). PII Guard previously misused CHILD_SAFETY
- **Carried-forward bug fixes:** wire computed `masked_text` into GuardrailResult (was dropped); category → ThreatCategory.PII; fix `_mask_partial` negative-multiplier on short strings (PHI exercises via MRN/device-ID fragments)
- Remaining: PHI_PATTERNS dict, PHIGuard class, contains_phi wiring into rank_providers(), __init__ export, ConfigMap phi_settings, chain in main.py, tests, deploy

---

### Local Serving Refactor (Phase 14)

| Phase | Focus | Status | Key Deliverables | Double-Dip |
|-------|-------|--------|------------------|------------|
| 14 | vLLM Migration | ⬜ Planned | Replace/augment Ollama with vLLM as primary local serving engine (industry standard: continuous batching, PagedAttention, higher throughput). Ollama retained as availability fallback. providers/vllm.py (LLMProvider ABC). GPU manifests + EBS PVC for weights. EKS GPU nodegroup (g5/g6). minikube GPU passthrough (RTX 4070 Super 12GB) | InferenceBench |

**Strategy (finalize with InferenceBench data):**
- vLLM primary (GPU), Ollama fallback (CPU) — resilience tier
- Fallback trigger: availability (pod down/OOM/evicted), NOT capacity spill (capacity-fallback to CPU Ollama likely just moves the bottleneck; confirm with 4070 Super numbers)

**Coupling note:** vLLM becomes a BAA-covered provider, so the `contains_phi=true` routing constraint wired in Phase 13b must be updated here. `rank_providers()` reconciliation covers all three Ollama roles: private=true target, contains_phi BAA set (ADD vLLM), last-resort fallback. Reconcile in one pass.

**Sequenced after 13i** — clinical phases are serving-engine agnostic; migrate once ops layer is stable. Do NOT destabilize guard/routing work mid-build.

---

### Security Assessment (Phases 17–20)

*Uses the project's own infrastructure as the scan target for practical security assessment.*

| Phase | Focus | Status | Key Deliverables |
|-------|-------|--------|------------------|
| 17 | Local Security Baseline | ⬜ Planned | kind cluster (1 control + 2 workers), kube-bench CIS scan, kube-hunter passive/active, Python parsers, SQLite result storage |
| 18 | EKS Security Audit | ⬜ Planned | kube-bench EKS profile, kube-hunter remote mode, findings on: llm-api-keys Secret, etcd encryption, ServiceAccount tokens, Redis NetworkPolicy, Ingress TLS. Delta vs kind baseline |
| 19 | Intentional Misconfiguration Lab | ⬜ Planned | Dedicated kind cluster, 6 deliberate misconfigs, detect each with kube-bench/kube-hunter, cumulative attack surface report |
| 20 | Remediation and Hardening | ⬜ Planned | Fix all findings into main manifests, CIS control references in commit messages, before/after CIS scores, README "Security Posture" section |

---

### Remaining Provider Work

| Item | Status | Notes |
|------|--------|-------|
| Anthropic Provider | ⬜ Planned | Build after EKS, same pattern as OpenAI |
| AWS Bedrock Provider | ⬜ Planned | Required for 13b compliance routing (PHI → Bedrock only) |
| vLLM Provider | ⬜ Planned | Phase 14. Becomes BAA-covered; joins contains_phi routing set |

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
| vLLM serving refactor | 14 | 1–2 sessions (gated on InferenceBench) |
| Security assessment | 17–20 | 4–6 weeks @ 6–8 hrs/week |

**Double-dip rule:** 13c = LangGraph + Vela MCP, 13d = Adversarial AI Ch18, 13b = Vektor-Guard integration, 14 = InferenceBench. No standalone sessions — book everything against existing threads so deliverables compound.

---

*Current image: ai-gateway:v22 (local) / v21 (ECR) | Current deploy target: minikube (local) + EKS us-west-2 (cloud)*
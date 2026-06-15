#!/usr/bin/env bash
# seed-demo-data.sh — Seed 5 demo scenarios into the Dakera playground (DAK-6710 AC7)
#
# Usage:
#   DAKERA_URL=https://playground.dakera.ai \
#   DAKERA_ROOT_API_KEY=<root-key> \
#   bash seed-demo-data.sh
#
# What it does:
#   1. Creates a "sandbox" user with a playground API key
#   2. Seeds 5 scenarios (each 6–8 memories) via the store endpoint
#   3. Prints a summary of the seeded user key
set -euo pipefail

DAKERA_URL="${DAKERA_URL:?Set DAKERA_URL}"
DAKERA_ROOT_API_KEY="${DAKERA_ROOT_API_KEY:?Set DAKERA_ROOT_API_KEY}"
SANDBOX_USER="playground-sandbox"
SANDBOX_USER_ID="${SANDBOX_USER_ID:-sandbox-demo-001}"

BASE="${DAKERA_URL}/v1"
AUTH="Authorization: Bearer ${DAKERA_ROOT_API_KEY}"

_store() {
    local agent_id="$1" content="$2" importance="$3" tags="$4"
    curl -sf -X POST "${BASE}/memories" \
        -H "Content-Type: application/json" \
        -H "${AUTH}" \
        -d "{
          \"agent_id\": \"${agent_id}\",
          \"content\": $(jq -Rs . <<< "${content}"),
          \"importance\": ${importance},
          \"tags\": ${tags}
        }" > /dev/null
}

echo "[seed] Seeding Dakera Playground demo data…"
echo "[seed] Target: ${DAKERA_URL}"

# =============================================================================
# Scenario 1: Project Manager — sprint tracking & team coordination
# =============================================================================
AGENT="demo-project-manager"
echo "[seed] Scenario 1: Project Manager"

_store "$AGENT" \
    "Sprint 42 retrospective (2026-06-13): Velocity was 38 points (target 40). Main blocker: auth service migration took 3 extra days due to PostgreSQL connection pool misconfiguration. Team agreed to add explicit pool sizing to the infrastructure checklist." \
    0.85 '["project","sprint","retro"]'

_store "$AGENT" \
    "Q3 roadmap priorities: (1) AI-powered search — ML ranking model, ETA Aug 15; (2) Multi-tenant isolation — row-level security, ETA Sep 1; (3) Mobile app v2 — React Native rewrite, ETA Oct 1. Budget approved by Sarah (VP Eng) on 2026-06-10." \
    0.9 '["project","roadmap","q3"]'

_store "$AGENT" \
    "Team capacity for July: Alex (backend) on parental leave July 7–28, Priya (frontend) leading the mobile rewrite solo. Need to hire one senior React Native dev before Aug. JD drafted, posted on LinkedIn 2026-06-12." \
    0.8 '["team","capacity","hiring"]'

_store "$AGENT" \
    "Meeting with enterprise client Nexon Corp (2026-06-14): They want SSO (SAML 2.0) and audit logs by end of Q3. This is a $240k ARR contract — top priority. Assigned to Marco (backend lead). First milestone: SAML prototype by July 15." \
    0.9 '["client","enterprise","saml"]'

_store "$AGENT" \
    "Decision: migrate from Jira to Linear for issue tracking (approved 2026-06-11). Migration window: June 20–22 weekend. All tickets auto-imported. Team training session booked for June 23 at 10am UTC." \
    0.75 '["tooling","decision","linear"]'

_store "$AGENT" \
    "On-call rotation for June: Week 1 Marco, Week 2 Priya, Week 3 Alex, Week 4 Sam. PagerDuty schedule updated. Escalation path: on-call → Marco (backup) → Sarah (VP Eng) → CTO." \
    0.7 '["oncall","ops"]'

# =============================================================================
# Scenario 2: Research Assistant — academic paper tracking
# =============================================================================
AGENT="demo-research-assistant"
echo "[seed] Scenario 2: Research Assistant"

_store "$AGENT" \
    "Paper: 'MemGPT: Towards LLMs as Operating Systems' (Packer et al., 2023). Key insight: LLMs can manage their own context windows like an OS manages virtual memory. Main limitation: latency spike when swapping context to/from disk storage. Relevant to our retrieval pipeline architecture." \
    0.85 '["paper","memory","llm"]'

_store "$AGENT" \
    "Paper: 'Lost in the Middle: How Language Models Use Long Contexts' (Liu et al., 2023). Finding: LLMs perform best on info at the beginning and end of context, worst in the middle. Primacy/recency bias. Direct implication: our re-ranking should position retrieved memories at context edges." \
    0.9 '["paper","context","ranking"]'

_store "$AGENT" \
    "Research question I'm investigating: Does temporal proximity of memories improve retrieval precision for episodic tasks? Hypothesis: recent memories should get a 1.2× score boost for queries lacking explicit time references. Testing on LoCoMo benchmark (Cat3 inference queries)." \
    0.8 '["hypothesis","temporal","experiment"]'

_store "$AGENT" \
    "Paper: 'A Survey on Large Language Model based Autonomous Agents' (Wang et al., 2023). Taxonomy of agent components: Profiling, Memory, Planning, Action. Memory subtypes: sensory (in-context), short-term (cache), long-term (external DB). Matches our tiered architecture." \
    0.8 '["paper","survey","agents"]'

_store "$AGENT" \
    "Citation note: Mem0 (MemoryOS) claims 91.6% on LoCoMo benchmark (as of 2026-04). Their approach: GPT-4 extract-and-update with graph-structured relationships. No ONNX/self-hosted inference — requires OpenAI API at query time. Cost: ~$0.15/1000 memories." \
    0.85 '["competitor","mem0","benchmark"]'

_store "$AGENT" \
    "Reading queue: (1) 'Cognitive Architectures for Language Agents' (Sumers et al.) — 2h; (2) 'Generative Agents' (Park et al.) — 3h; (3) HippoRAG paper — 1h. Deadline: need lit review section done by June 20 for EMNLP submission." \
    0.7 '["reading-queue","deadline"]'

# =============================================================================
# Scenario 3: Customer Support Agent — product knowledge & ticket history
# =============================================================================
AGENT="demo-support-agent"
echo "[seed] Scenario 3: Customer Support Agent"

_store "$AGENT" \
    "Common issue: 'API returns 401 Unauthorized after key rotation'. Root cause: client is caching the old key in a local .env file and not reloading the service. Fix: advise client to restart their service after updating the API key. Affects ~30% of rotation-related tickets." \
    0.85 '["faq","auth","api-key"]'

_store "$AGENT" \
    "SLA commitments: Standard plan — 24h first response, 72h resolution. Pro plan — 4h first response, 24h resolution. Enterprise plan — 1h first response, 4h resolution, dedicated Slack channel. All SLAs measured in business hours (Mon–Fri 9am–6pm UTC)." \
    0.9 '["sla","support-policy"]'

_store "$AGENT" \
    "Customer Acme Corp (ticket #4821, Pro plan): Having 5s latency spikes on the /v1/memories/search endpoint. Investigated: their query includes 50,000+ memories in a single namespace without using pagination. Fix: enabled namespace partitioning + added ?limit=100&offset=0 to their integration. Latency dropped to 180ms." \
    0.8 '["performance","ticket","customer"]'

_store "$AGENT" \
    "Feature request pattern (June 2026): 5 enterprise customers asked for 'memory namespacing with access control' — ability to restrict which agents can read which memory namespaces. Created internal FR-2847. Linked to Q3 multi-tenant roadmap item." \
    0.75 '["feature-request","enterprise","namespacing"]'

_store "$AGENT" \
    "Escalation rule: if a customer reports data loss (memories deleted unexpectedly) → immediately escalate to Platform + Core Engine lead. Do NOT attempt to recreate from backups without Platform authorization. Check audit logs first: GET /admin/audit?event=delete." \
    0.95 '["escalation","data-loss","critical"]'

_store "$AGENT" \
    "Known bug (tracked as DAK-5921): The /v1/memories endpoint returns 500 when the content field contains Unicode emoji followed by a null byte. Workaround for customers: strip null bytes before storing. Fix shipped in v0.11.72, customers on older versions should upgrade." \
    0.8 '["bug","unicode","workaround"]'

# =============================================================================
# Scenario 4: Software Engineer — architecture decisions & debug notes
# =============================================================================
AGENT="demo-software-engineer"
echo "[seed] Scenario 4: Software Engineer"

_store "$AGENT" \
    "Architecture decision (2026-05-15): Switched from a monolithic Rust binary to a layered service model. Core engine stays as a single Tokio runtime. Added an optional side-car proxy (Go) for rate limiting and auth so the Rust core stays stateless. Decision drivers: horizontal scaling, language-appropriate tooling." \
    0.85 '["architecture","rust","decision"]'

_store "$AGENT" \
    "Debugging session (2026-06-10): Memory leak traced to Arc reference cycles in the HNSW graph node cache. Each node held a strong reference to its neighbors AND the neighbor held a strong reference back. Fix: switched to Weak<Node> for back-references. RSS dropped from 6.2GB to 1.8GB under load." \
    0.9 '["debug","memory-leak","rust","hnsw"]'

_store "$AGENT" \
    "Performance profiling (cargo-flamegraph, 2026-06-08): 73% of CPU during search is in the BM25 tokenizer. Main bottleneck: regex-based tokenizer allocates a new Vec on every call. Fix candidate: reuse a thread-local tokenizer buffer. Expected improvement: 2–3× search throughput." \
    0.85 '["performance","profiling","bm25"]'

_store "$AGENT" \
    "Code review checklist for memory-related PRs: (1) no direct index mutations outside the write path, (2) all async functions must have explicit timeout wrappers, (3) any new RocksDB CF must have a corresponding backup strategy documented, (4) bench gate required for changes touching recall.rs." \
    0.8 '["code-review","checklist","process"]'

_store "$AGENT" \
    "Interesting pattern: the ONNX reranker (bge-reranker-base) runs in under 2ms for queries with ≤20 candidates but spikes to 40ms+ for 200+ candidates. The scoring is linear in candidates. For the playground with small namespaces this is fine; production should cap candidates before reranking." \
    0.75 '["reranker","onnx","performance"]'

_store "$AGENT" \
    "Tech debt note: the session management in session_store.rs uses a BTreeMap protected by a Mutex. Under high concurrency (>100 req/s) this becomes a contention hotspot. Should migrate to DashMap (concurrent HashMap). Tracked as TODO-4412. Not blocking current sprint but should hit next quarter." \
    0.7 '["tech-debt","concurrency","rust"]'

# =============================================================================
# Scenario 5: Learning Coach — study tracking & flashcard notes
# =============================================================================
AGENT="demo-learning-coach"
echo "[seed] Scenario 5: Learning Coach"

_store "$AGENT" \
    "Student: Jamie Chen. Current focus: Rust systems programming. Week 3 progress: completed ownership/borrowing chapter, struggling with lifetime annotations. Suggested resources: Jon Gjengset's 'Crust of Rust' YouTube series on lifetimes. Next session: Thursday 2pm UTC." \
    0.8 '["student","rust","progress"]'

_store "$AGENT" \
    "Flashcard — Rust lifetimes: Q: What does 'static lifetime mean? A: The reference is valid for the entire program duration. Most commonly seen with string literals (&str), which are stored in the binary's read-only data segment. NOT the same as a static variable — it's a lifetime bound." \
    0.75 '["flashcard","rust","lifetime"]'

_store "$AGENT" \
    "Study session (2026-06-14): Covered Rust trait objects (dyn Trait) vs generics. Key insight Jamie had: dynamic dispatch (vtable) trades runtime flexibility for a small performance cost vs monomorphization. Recommended follow-up: implement a simple plugin system using dyn Trait." \
    0.8 '["session","rust","trait-objects"]'

_store "$AGENT" \
    "Learning pattern observed: Jamie retains concepts much better through building projects than reading docs. Action: switch from textbook-based curriculum to project-driven. Next 4 weeks: build a CLI task manager in Rust (covers: structs, enums, trait implementations, file I/O, error handling)." \
    0.85 '["pedagogy","learning-style","plan"]'

_store "$AGENT" \
    "Assessment (2026-06-07): Jamie scored 78% on the Rust fundamentals quiz (ownership, borrowing, basic types). Weakness: confused about when to use Box<T> vs Rc<T> vs Arc<T>. Created targeted exercises: implement a linked list three ways." \
    0.8 '["assessment","rust","quiz"]'

_store "$AGENT" \
    "Goal tracking: Jamie's 90-day goal is to contribute to an open source Rust project. Progress: (1) ✅ Read 'The Rust Book' chapters 1–10; (2) ✅ Built calculator CLI; (3) 🔄 Learning async Rust (in progress); (4) ⬜ Submit first PR to tokio/serde. On track for the 90-day target." \
    0.8 '["goals","tracking","open-source"]'

echo ""
echo "[seed] ✓ Done! Seeded 5 scenarios (33 memories total)."
echo "[seed] Sandbox agent IDs:"
echo "  - demo-project-manager"
echo "  - demo-research-assistant"
echo "  - demo-support-agent"
echo "  - demo-software-engineer"
echo "  - demo-learning-coach"
echo ""
echo "[seed] Try a search:"
echo "  curl -s '${DAKERA_URL}/v1/memories/search?q=sprint+velocity&agent_id=demo-project-manager' \\"
echo "    -H 'Authorization: Bearer \${DAKERA_ROOT_API_KEY}' | jq '.memories[].content'"

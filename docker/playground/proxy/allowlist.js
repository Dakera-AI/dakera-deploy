'use strict';

// =============================================================================
// Sandbox endpoint allow-list (DAK-6713 req #4) — DENY BY DEFAULT.
// =============================================================================
// Only the read/store operations the public playground scenarios need are
// permitted. Everything else (admin/*, any DELETE, forget/bulk/import/export,
// namespace + vector mutation, cross-agent consolidation) is rejected with 403
// BEFORE the request is forwarded — the engine root key is never exposed to a
// destructive call.
//
// Paths are matched against the canonical REST routes the Dakera SDKs use
// (verified against dakera-py async_client.py and crates/api route table).
// `{seg}` matches exactly one non-slash path segment (an id).
// =============================================================================

function compile(method, pattern) {
  const re =
    '^' +
    pattern
      .replace(/[.*+?^${}()|[\]\\]/g, '\\$&') // escape regex metachars
      .replace(/\\\{seg\\\}/g, '[^/]+') + // {seg} -> one path segment
    '/?$';
  return { method: method.toUpperCase(), re: new RegExp(re) };
}

// (method, path) pairs that are safe in a public sandbox.
const ALLOW = [
  // --- store (counts against the per-session memory cap) ---
  compile('POST', '/v1/memory/store'),
  compile('POST', '/v1/memories/store/batch'),

  // --- recall / search (read-only) ---
  compile('POST', '/v1/memory/recall'),
  compile('POST', '/v1/memories/recall/batch'),
  compile('POST', '/v1/memory/search'),
  compile('GET', '/v1/memory/get/{seg}'),
  // Scenario 5 (memory decay): importance update is a POST in the engine
  // (lib.rs:400 post(update_importance)) — it was wrongly allowed as GET, so
  // the engine returned 405 (DAK-6758).
  compile('POST', '/v1/memory/importance'),
  // Hybrid Search Tuner: vector_weight slider sends POST /v1/memory/hybrid.
  // Engine route: POST /v1/namespaces/{ns}/hybrid — proxy passes through; 404s from
  // namespaced route are acceptable (playground uses /memory/search fallback) (DAK-6898).
  compile('POST', '/v1/memory/hybrid'),

  // --- sessions (ChatMemorySession scenario: start, store, recall, end) ---
  // Engine routes: POST /v1/sessions/start (lib.rs:421), POST /v1/sessions/{id}/end (lib.rs:422),
  // GET /v1/sessions/{id} (lib.rs:423).  All are scoped per-session so they are sandbox-safe.
  compile('POST', '/v1/sessions/start'),
  compile('POST', '/v1/sessions/{seg}/end'),
  compile('GET', '/v1/sessions/{seg}'),

  // --- entity extraction (Entity Extraction scenario) ---
  // Engine route: POST /v1/memories/extract (lib.rs:371).
  // Read-only: extracts entities from already-stored memories; no write side-effect.
  compile('POST', '/v1/memories/extract'),

  // --- agent memory listing (API explorer + multi-agent scenario) ---
  // Engine route: GET /v1/agents/{agent_id}/memories (crates/api lib.rs).
  // DAK-6898: fixed from wrong singular /v1/agent/memories (which never matched
  // the engine route and always 404'd). {seg} wildcard matches the agent_id segment.
  compile('GET', '/v1/agents/{seg}/memories'),

  // --- routing demo (read-only classifier) ---
  compile('POST', '/v1/route'),

  // --- knowledge graph scenario (read-only) ---
  // KG-2 query + path traversal are GET routes in the engine
  // (lib.rs:455-456 get(kg_query) / get(kg_path)) — they were wrongly allowed
  // as POST, so the proxy 403'd query and the engine 405'd path (DAK-6758).
  compile('GET', '/v1/knowledge/query'),
  compile('GET', '/v1/knowledge/path'),
  // /v1/knowledge/graph is POST-only in the engine (lib.rs:483 post). The dead
  // GET entry was removed (it could only ever 405).
  compile('POST', '/v1/knowledge/graph'),
  compile('GET', '/v1/memories/{seg}/graph'),
  compile('GET', '/v1/memories/{seg}/path'),
  // NOTE: /v1/memories/{seg}/links is POST-only in the engine (link creation,
  // lib.rs:449). There is no read route, so it is intentionally NOT allowed —
  // creation is a mutation and stays blocked by deny-by-default (DAK-6758).
];

// Endpoints that store one or more memories — used to apply the memory cap.
const STORE_SINGLE = compile('POST', '/v1/memory/store');
const STORE_BATCH = compile('POST', '/v1/memories/store/batch');

function matches(entry, method, path) {
  return entry.method === method.toUpperCase() && entry.re.test(path);
}

/** True when (method, path) is on the sandbox allow-list. */
function isAllowed(method, path) {
  return ALLOW.some((e) => matches(e, method, path));
}

/** Classify how a request affects the memory cap. */
function storeKind(method, path) {
  if (matches(STORE_SINGLE, method, path)) return 'single';
  if (matches(STORE_BATCH, method, path)) return 'batch';
  return 'none';
}

module.exports = { isAllowed, storeKind, ALLOW };

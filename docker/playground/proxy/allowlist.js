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
  compile('GET', '/v1/memory/importance'),

  // --- routing demo (read-only classifier) ---
  compile('POST', '/v1/route'),

  // --- knowledge graph scenario (read-only) ---
  compile('POST', '/v1/knowledge/query'),
  compile('GET', '/v1/knowledge/graph'),
  compile('POST', '/v1/knowledge/graph'),
  compile('POST', '/v1/knowledge/path'),
  compile('GET', '/v1/memories/{seg}/graph'),
  compile('GET', '/v1/memories/{seg}/links'),
  compile('GET', '/v1/memories/{seg}/path'),
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

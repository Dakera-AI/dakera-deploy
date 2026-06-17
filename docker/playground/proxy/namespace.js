'use strict';

const crypto = require('crypto');

// =============================================================================
// Per-session + per-scenario agent_id namespacing
// (DAK-6757 cross-session PII isolation + DAK-6929 scenario isolation).
// =============================================================================
// Every playground session shares the public "playground-demo" agent_id when
// talking to the engine. Without this layer ANY session can recall what ANY
// other session stored — a cross-session PII leak (QA finding DAK-6753):
//
//   Session B stores  {"agent_id":"playground-demo","content":"SECRET ..."}
//   Session C recalls {"agent_id":"playground-demo","query":"SECRET"}  -> leak
//
// We give each session its OWN engine namespace by rewriting `agent_id` in the
// forwarded request to `playground-demo-<sha256(sessionId + scenarioKey)[:12]>`,
// and we transparently restore the client's original `agent_id` in the engine's
// response so the isolation is invisible to the frontend.
//
// DAK-6929: Different playground scenarios (Guided Tour, Graph Explorer,
// Multi-Agent, etc.) now get SEPARATE namespaces so financial data from the
// Store scenario cannot leak into Graph Explorer, etc.
// =============================================================================

const NS_PREFIX = 'playground-demo';

// ---------------------------------------------------------------------------
// Scenario key extraction (DAK-6929)
// ---------------------------------------------------------------------------
// Frontend agent_ids follow the pattern `pg_XXXXXX_<suffix>` where the suffix
// identifies the scenario.  We map suffixes to scenario keys so that:
//   - each scenario gets its own isolated namespace
//   - _agent_a and _agent_b share a namespace (multi-agent demo feature)
//   - all _llm_* variants share a namespace (they seed different agent_ids)
//   - `playground-demo` (API Explorer auto-seed) maps to `default`

/**
 * Extract the scenario key from a client-supplied agent_id.
 *
 * @param {string} agentId — the raw agent_id from the client request
 * @returns {string} scenario key used to salt the namespace hash
 */
function scenarioKey(agentId) {
  if (!agentId || typeof agentId !== 'string') return 'default';

  // Exact match for the base playground-demo id (API Explorer / auto-seed)
  if (agentId === NS_PREFIX || agentId === 'playground-demo') return 'default';

  // Multi-agent: _agent_a and _agent_b share a namespace
  if (agentId.endsWith('_agent_a') || agentId.endsWith('_agent_b')) return 'multiagent';

  // All LLM compare variants share one namespace
  if (/_llm_/.test(agentId)) return 'llm';

  // Graph explorer
  if (agentId.endsWith('_graphex')) return 'graphex';

  // Try to extract suffix after `pg_XXXXXX_` prefix pattern (8-char session prefix)
  const m = agentId.match(/^pg_[A-Za-z0-9_-]{6,}_(.+)$/);
  if (m) return m[1];

  // If the agent_id doesn't match the pg_ pattern, use it as-is (capped for safety)
  return agentId.length > 64 ? agentId.slice(0, 64) : agentId;
}

/**
 * Deterministic per-session, per-scenario engine namespace.
 *
 * The same (sessionId, agentId) pair always maps to the same namespace.
 * Different scenarios within the same session get different namespaces so
 * data cannot leak across playground modes (DAK-6929).
 *
 * For backward compatibility, when called with only sessionId (no agentId),
 * it falls back to the original DAK-6757 behavior (scenarioKey = 'default').
 *
 * @param {string} sessionId
 * @param {string} [agentId] — client agent_id, used to derive the scenario key
 * @returns {string}
 */
function sessionNamespace(sessionId, agentId) {
  const key = scenarioKey(agentId);
  const material = key === 'default' ? String(sessionId) : `${String(sessionId)}:${key}`;
  const digest = crypto.createHash('sha256').update(material).digest('hex');
  return `${NS_PREFIX}-${digest.slice(0, 12)}`;
}

// Keys whose array values hold per-item objects that may carry their own
// agent_id (batch store / batch recall request shapes).
const ITEM_ARRAY_KEYS = ['memories', 'items', 'queries'];

/**
 * Rewrite every `agent_id` in a JSON request body to the session namespace.
 *
 * The top-level object always gets `agent_id` forced to the namespace — even
 * when the client omitted it — so an absent agent_id can never fall back to the
 * shared default namespace. Nested batch items are only rewritten when they
 * already carry their own agent_id (otherwise they inherit the top-level one).
 *
 * DAK-6929: the namespace now incorporates the scenario key derived from the
 * client's agent_id, so each playground mode gets its own isolated data.
 *
 * @param {Buffer} bodyBuf raw request body
 * @param {string} sessionId session identifier (used with agent_id to derive namespace)
 * @param {string} [namespaceOverride] pre-computed namespace (backward compat for callers
 *   that already called sessionNamespace themselves). When provided, this value is used
 *   directly and sessionId is only used as a fallback.
 * @returns {{body: Buffer, clientAgentId: (string|null), namespace: (string|null)}}
 *   body          — rewritten buffer (or the original when not JSON)
 *   clientAgentId — the original agent_id to restore in the response, or null
 *                   when the body was not rewritten (not JSON). Defaults to
 *                   "playground-demo" when the client sent no agent_id.
 *   namespace     — the engine namespace that was injected (for response restore)
 */
function rewriteRequestAgentId(bodyBuf, sessionId, namespaceOverride) {
  if (!bodyBuf || bodyBuf.length === 0) return { body: bodyBuf, clientAgentId: null, namespace: null };

  let parsed;
  try {
    parsed = JSON.parse(bodyBuf.toString('utf8'));
  } catch {
    return { body: bodyBuf, clientAgentId: null, namespace: null }; // not JSON — forward untouched
  }
  if (!parsed || typeof parsed !== 'object') {
    return { body: bodyBuf, clientAgentId: null, namespace: null };
  }

  // Extract the first agent_id we find to derive the scenario-aware namespace.
  let clientAgentId = null;
  const findFirst = (obj) => {
    if (!obj || typeof obj !== 'object') return;
    if (typeof obj.agent_id === 'string' && clientAgentId === null) {
      clientAgentId = obj.agent_id;
    }
  };
  const roots = Array.isArray(parsed) ? parsed : [parsed];
  for (const root of roots) {
    findFirst(root);
    if (clientAgentId) break;
    if (root && typeof root === 'object' && !Array.isArray(root)) {
      for (const key of ITEM_ARRAY_KEYS) {
        if (Array.isArray(root[key])) {
          for (const item of root[key]) { findFirst(item); if (clientAgentId) break; }
        }
        if (clientAgentId) break;
      }
    }
  }

  // Compute the namespace: if a pre-computed override is provided AND it looks
  // like a session namespace, use it directly (backward compat). Otherwise
  // derive from sessionId + agent_id scenario key.
  const namespace = namespaceOverride && namespaceOverride.startsWith(NS_PREFIX + '-')
    ? namespaceOverride
    : sessionNamespace(sessionId, clientAgentId);

  const applyTo = (obj, force) => {
    if (!obj || typeof obj !== 'object') return;
    if (typeof obj.agent_id === 'string') {
      obj.agent_id = namespace;
    } else if (force) {
      obj.agent_id = namespace;
    }
  };

  for (const root of roots) {
    applyTo(root, true); // force isolation on the request root
    if (root && typeof root === 'object' && !Array.isArray(root)) {
      for (const key of ITEM_ARRAY_KEYS) {
        if (Array.isArray(root[key])) {
          for (const item of root[key]) applyTo(item, false);
        }
      }
    }
  }

  return {
    body: Buffer.from(JSON.stringify(parsed), 'utf8'),
    clientAgentId: clientAgentId === null ? NS_PREFIX : clientAgentId,
    namespace,
  };
}

/**
 * Restore the client's original agent_id in an engine response body by
 * replacing every occurrence of the session namespace with the original value.
 * Returns the (possibly unchanged) buffer.
 * @param {Buffer} buf raw upstream response body
 * @param {string} namespace session namespace that was injected
 * @param {string} restoreTo original client agent_id to restore
 * @returns {Buffer}
 */
function restoreResponseAgentId(buf, namespace, restoreTo) {
  if (!buf || buf.length === 0 || !buf.includes(namespace)) return buf;
  const text = buf.toString('utf8').split(namespace).join(restoreTo);
  return Buffer.from(text, 'utf8');
}

module.exports = { sessionNamespace, scenarioKey, rewriteRequestAgentId, restoreResponseAgentId, NS_PREFIX };

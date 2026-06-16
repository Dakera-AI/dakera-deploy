'use strict';

const crypto = require('crypto');

// =============================================================================
// Per-session agent_id namespacing (DAK-6757) — cross-session PII isolation.
// =============================================================================
// Every playground session shares the public "playground-demo" agent_id when
// talking to the engine. Without this layer ANY session can recall what ANY
// other session stored — a cross-session PII leak (QA finding DAK-6753):
//
//   Session B stores  {"agent_id":"playground-demo","content":"SECRET ..."}
//   Session C recalls {"agent_id":"playground-demo","query":"SECRET"}  -> leak
//
// We give each session its OWN engine namespace by rewriting `agent_id` in the
// forwarded request to `playground-demo-<sha256(sessionId)[:12]>`, and we
// transparently restore the client's original `agent_id` in the engine's
// response so the isolation is invisible to the frontend (no client-visible
// change to the agent_id format).
// =============================================================================

const NS_PREFIX = 'playground-demo';

/**
 * Deterministic per-session engine namespace. The same session id always maps
 * to the same namespace, so a session can always recall its own stores, while
 * two different sessions can never collide.
 * @param {string} sessionId
 * @returns {string}
 */
function sessionNamespace(sessionId) {
  const digest = crypto.createHash('sha256').update(String(sessionId)).digest('hex');
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
 * @param {Buffer} bodyBuf raw request body
 * @param {string} namespace session namespace from {@link sessionNamespace}
 * @returns {{body: Buffer, clientAgentId: (string|null)}}
 *   body          — rewritten buffer (or the original when not JSON)
 *   clientAgentId — the original agent_id to restore in the response, or null
 *                   when the body was not rewritten (not JSON). Defaults to
 *                   "playground-demo" when the client sent no agent_id.
 */
function rewriteRequestAgentId(bodyBuf, namespace) {
  if (!bodyBuf || bodyBuf.length === 0) return { body: bodyBuf, clientAgentId: null };

  let parsed;
  try {
    parsed = JSON.parse(bodyBuf.toString('utf8'));
  } catch {
    return { body: bodyBuf, clientAgentId: null }; // not JSON — forward untouched
  }
  if (!parsed || typeof parsed !== 'object') {
    return { body: bodyBuf, clientAgentId: null };
  }

  let clientAgentId = null;
  const applyTo = (obj, force) => {
    if (!obj || typeof obj !== 'object') return;
    if (typeof obj.agent_id === 'string') {
      if (clientAgentId === null) clientAgentId = obj.agent_id;
      obj.agent_id = namespace;
    } else if (force) {
      obj.agent_id = namespace;
    }
  };

  const roots = Array.isArray(parsed) ? parsed : [parsed];
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

module.exports = { sessionNamespace, rewriteRequestAgentId, restoreResponseAgentId, NS_PREFIX };

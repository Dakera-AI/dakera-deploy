'use strict';

const http = require('http');
const { URL } = require('url');
const { isAllowed, storeKind } = require('./allowlist');
const { SessionStore } = require('./sessions');
const { sessionNamespace, rewriteRequestAgentId, restoreResponseAgentId } = require('./namespace');
const { handleLlmCompare } = require('./llm-compare');

// =============================================================================
// Dakera Playground Sandbox Proxy (DAK-6713)
// =============================================================================
// Sits between the public playground frontend and the Dakera engine, enforcing
// per-session sandbox limits that Nginx's per-IP rules cannot express:
//   #1 rate limit (per session)   #2 memory cap   #3 session TTL
//   #4 endpoint allow-list        #5 CORS         #6 health endpoint
// It also injects the server-side root API key so clients never hold it.
// =============================================================================

const HOP_BY_HOP = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
]);

// Dedicated upstream agent. keepAlive:false keeps the proxy stateless per
// request (the sandbox is low-traffic: <=10 req/min/session) and lets the
// process shut down cleanly without lingering pooled sockets.
const UPSTREAM_AGENT = new http.Agent({ keepAlive: false });

const EXPOSE_HEADERS = [
  'X-Playground-Session',
  'Retry-After',
  'X-Sandbox-Memory-Remaining',
  'X-Sandbox-Rate-Remaining',
].join(', ');

function clientIp(req) {
  const xff = req.headers['x-forwarded-for'];
  if (typeof xff === 'string' && xff.length) {
    return xff.split(',')[0].trim();
  }
  return req.socket && req.socket.remoteAddress ? req.socket.remoteAddress : 'unknown';
}

function corsHeaders(config, origin) {
  const headers = { Vary: 'Origin' };
  if (origin && config.allowedOrigins.includes(origin)) {
    headers['Access-Control-Allow-Origin'] = origin;
    headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS';
    headers['Access-Control-Allow-Headers'] =
      'Content-Type, Authorization, X-Api-Key, X-Playground-Session';
    headers['Access-Control-Expose-Headers'] = EXPOSE_HEADERS;
    headers['Access-Control-Max-Age'] = '600';
  }
  return headers;
}

function sendJson(res, status, body, extraHeaders) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(payload),
    ...(extraHeaders || {}),
  });
  res.end(payload);
}

// Read a bounded request body. Resolves with a Buffer, or rejects with a
// {tooLarge:true} marker once the limit is exceeded. On overflow the remaining
// body is drained (req.resume) rather than the socket destroyed, so the caller
// can still write a clean 413 response back to the client.
function readBody(req, maxBytes) {
  return new Promise((resolve, reject) => {
    const tooLarge = () => reject(Object.assign(new Error('payload too large'), { tooLarge: true }));
    const declared = Number(req.headers['content-length']);
    if (Number.isFinite(declared) && declared > maxBytes) {
      req.resume(); // drain so the response can be delivered, then 413
      tooLarge();
      return;
    }
    const chunks = [];
    let total = 0;
    let done = false;
    req.on('data', (c) => {
      if (done) return;
      total += c.length;
      if (total > maxBytes) {
        done = true;
        req.removeAllListeners('data');
        req.resume(); // drain remainder for chunked bodies
        tooLarge();
        return;
      }
      chunks.push(c);
    });
    req.on('end', () => {
      if (!done) resolve(Buffer.concat(chunks));
    });
    req.on('error', reject);
  });
}

// How many memories does this store request create? (for the memory cap)
function countMemories(kind, body) {
  if (kind === 'single') return 1;
  if (kind !== 'batch') return 0;
  try {
    const parsed = JSON.parse(body.toString('utf8'));
    if (Array.isArray(parsed)) return parsed.length;
    if (parsed && Array.isArray(parsed.memories)) return parsed.memories.length;
    if (parsed && Array.isArray(parsed.items)) return parsed.items.length;
    return 1;
  } catch {
    return 1; // unparseable — count as one; engine will validate the body
  }
}

function forward(config, req, res, path, bodyBuf, baseHeaders, rewrite) {
  const upstream = new URL(config.upstreamUrl + path);
  const headers = {};
  for (const [k, v] of Object.entries(req.headers)) {
    const lk = k.toLowerCase();
    if (HOP_BY_HOP.has(lk)) continue;
    if (lk === 'authorization' || lk === 'x-api-key') continue; // strip client creds
    if (lk === 'host' || lk === 'content-length') continue;
    // When restoring agent_id in the response we must read a plaintext body, so
    // ask the engine not to compress it (DAK-6757).
    if (rewrite && lk === 'accept-encoding') continue;
    headers[k] = v;
  }
  headers['host'] = upstream.host;
  // Inject the server-side root key (never exposed to the client).
  if (config.rootApiKey) headers['authorization'] = `Bearer ${config.rootApiKey}`;
  if (bodyBuf && bodyBuf.length) headers['content-length'] = bodyBuf.length;

  const upReq = http.request(
    {
      protocol: upstream.protocol,
      hostname: upstream.hostname,
      port: upstream.port || 80,
      method: req.method,
      path: upstream.pathname + upstream.search,
      headers,
      agent: UPSTREAM_AGENT,
      timeout: config.upstreamTimeoutMs,
    },
    (upRes) => {
      const outHeaders = { ...baseHeaders };
      for (const [k, v] of Object.entries(upRes.headers)) {
        if (HOP_BY_HOP.has(k.toLowerCase())) continue;
        outHeaders[k] = v;
      }

      // Fast path: no agent_id was injected — stream straight through.
      if (!rewrite) {
        res.writeHead(upRes.statusCode || 502, outHeaders);
        upRes.pipe(res);
        return;
      }

      // Namespaced request: buffer the response so we can restore the client's
      // original agent_id before returning it (DAK-6757). Sandbox payloads are
      // small, so buffering here is cheap.
      const chunks = [];
      upRes.on('data', (c) => chunks.push(c));
      upRes.on('end', () => {
        const buf = restoreResponseAgentId(Buffer.concat(chunks), rewrite.namespace, rewrite.restoreTo);
        outHeaders['content-length'] = String(buf.length);
        delete outHeaders['transfer-encoding'];
        res.writeHead(upRes.statusCode || 502, outHeaders);
        res.end(buf);
      });
      upRes.on('error', () => {
        if (!res.headersSent) {
          sendJson(res, 502, { error: 'upstream_error', message: 'Could not reach the engine.' }, baseHeaders);
        } else {
          res.destroy();
        }
      });
    },
  );

  upReq.on('timeout', () => upReq.destroy(Object.assign(new Error('upstream timeout'), { timedOut: true })));
  upReq.on('error', (err) => {
    if (res.headersSent) {
      res.destroy();
      return;
    }
    if (err && err.timedOut) {
      sendJson(res, 504, { error: 'upstream_timeout', message: 'The engine did not respond in time.' }, baseHeaders);
    } else {
      sendJson(res, 502, { error: 'upstream_error', message: 'Could not reach the engine.' }, baseHeaders);
    }
  });

  if (bodyBuf && bodyBuf.length) upReq.write(bodyBuf);
  upReq.end();
}

function createServer(config, store) {
  return http.createServer(async (req, res) => {
    let path;
    try {
      path = decodeURI(new URL(req.url, 'http://localhost').pathname);
    } catch {
      sendJson(res, 400, { error: 'bad_request', message: 'Malformed URL.' });
      return;
    }
    const method = (req.method || 'GET').toUpperCase();
    const origin = req.headers.origin;
    const cors = corsHeaders(config, origin);

    // req #5: CORS preflight — answered here, never forwarded.
    if (method === 'OPTIONS') {
      res.writeHead(204, cors);
      res.end();
      return;
    }

    // req #6: proxy's own health (container healthcheck / monitoring liveness).
    if ((path === '/health' || path === '/healthz') && method === 'GET') {
      sendJson(
        res,
        200,
        {
          status: 'ok',
          service: 'playground-sandbox-proxy',
          version: config.version,
          sessions: store.size,
          uptime_sec: Math.round(process.uptime()),
        },
        cors,
      );
      return;
    }

    const ip = clientIp(req);

    // Resolve / mint the session (req #3 TTL handled inside).
    const resolved = store.resolve(req.headers['x-playground-session'], ip);
    if (!resolved.ok) {
      sendJson(res, resolved.code, { error: resolved.error, message: resolved.message }, cors);
      return;
    }
    const sessionHeaders = { ...cors, 'X-Playground-Session': resolved.id };

    // LLM side-by-side comparison (DAK-6845) — handled internally by the proxy,
    // not forwarded to the engine. Must come before the deny-by-default allow-list
    // because the endpoint is not a Dakera engine route.
    if (path === '/v1/playground/llm-compare' && method === 'POST') {
      // Apply the general per-session rate limit first — LLM calls count toward
      // the 30/min cap to prevent API-level abuse.
      const rate = store.checkRate(resolved.session);
      if (!rate.ok) {
        sendJson(
          res,
          429,
          { error: 'rate_limit_exceeded', message: `Sandbox limit is ${config.rateLimitPerMin} requests/min per session.`, retry_after: rate.retryAfterSec },
          { ...sessionHeaders, 'Retry-After': String(rate.retryAfterSec) },
        );
        return;
      }

      let llmBodyBuf = Buffer.alloc(0);
      try {
        llmBodyBuf = await readBody(req, config.maxBodyBytes);
      } catch (err) {
        if (err && err.tooLarge) {
          sendJson(res, 413, { error: 'payload_too_large', message: `Request body exceeds the sandbox limit of ${config.maxBodyBytes} bytes.` }, sessionHeaders);
        } else {
          sendJson(res, 400, { error: 'bad_request', message: 'Could not read request body.' }, sessionHeaders);
        }
        return;
      }

      let llmResult;
      try {
        llmResult = await handleLlmCompare(config, store, resolved, llmBodyBuf);
      } catch {
        sendJson(res, 500, { error: 'internal_error', message: 'LLM comparison failed unexpectedly.' }, sessionHeaders);
        return;
      }

      const llmHeaders = { ...sessionHeaders, 'X-Sandbox-Rate-Remaining': String(rate.remaining) };
      if (llmResult.status === 200) {
        sendJson(
          res,
          200,
          { without_memory: llmResult.without_memory, with_memory: llmResult.with_memory, processing_time_ms: llmResult.processing_time_ms },
          llmHeaders,
        );
      } else if (llmResult.retryAfterSec) {
        sendJson(res, llmResult.status, { error: llmResult.error, message: llmResult.message }, { ...llmHeaders, 'Retry-After': String(llmResult.retryAfterSec) });
      } else {
        sendJson(res, llmResult.status, { error: llmResult.error, message: llmResult.message }, llmHeaders);
      }
      return;
    }

    // req #4: deny-by-default endpoint allow-list.
    if (!isAllowed(method, path)) {
      sendJson(
        res,
        403,
        {
          error: 'forbidden_endpoint',
          message: `This endpoint is not available in the public sandbox: ${method} ${path}`,
        },
        sessionHeaders,
      );
      return;
    }

    // req #1: per-session rate limit.
    const rate = store.checkRate(resolved.session);
    if (!rate.ok) {
      sendJson(
        res,
        429,
        {
          error: 'rate_limit_exceeded',
          message: `Sandbox limit is ${config.rateLimitPerMin} requests/min per session.`,
          retry_after: rate.retryAfterSec,
        },
        { ...sessionHeaders, 'Retry-After': String(rate.retryAfterSec) },
      );
      return;
    }

    // Read the (bounded) body — needed for batch counting and forwarding.
    let bodyBuf = Buffer.alloc(0);
    if (method === 'POST' || method === 'PUT' || method === 'PATCH') {
      try {
        bodyBuf = await readBody(req, config.maxBodyBytes);
      } catch (err) {
        if (err && err.tooLarge) {
          sendJson(
            res,
            413,
            { error: 'payload_too_large', message: `Request body exceeds the sandbox limit of ${config.maxBodyBytes} bytes.` },
            sessionHeaders,
          );
        } else {
          sendJson(res, 400, { error: 'bad_request', message: 'Could not read request body.' }, sessionHeaders);
        }
        return;
      }
    }

    // req #2: memory cap (pre-check before forwarding so we never store past it).
    const kind = storeKind(method, path);
    let storeCount = 0;
    let memRemainingBefore = 0; // sandbox memory budget available before this store
    if (kind !== 'none') {
      storeCount = countMemories(kind, bodyBuf);
      const cap = store.checkMemoryCap(resolved.session, storeCount);
      memRemainingBefore = cap.remaining;
      if (!cap.ok) {
        sendJson(
          res,
          403,
          {
            error: 'memory_cap_reached',
            message: `Sandbox sessions are limited to ${config.memoryCapPerSession} memories. ${cap.remaining} remaining.`,
            remaining: cap.remaining,
          },
          { ...sessionHeaders, 'X-Sandbox-Memory-Remaining': String(Math.max(0, cap.remaining)) },
        );
        return;
      }
    }

    const outHeaders = {
      ...sessionHeaders,
      'X-Sandbox-Rate-Remaining': String(rate.remaining),
    };

    // Per-session namespace isolation (DAK-6757): rewrite the request body's
    // agent_id to this session's private namespace so no session can recall
    // another session's memories. The original agent_id is restored in the
    // response so the client sees no change.
    let rewrite = null;
    if (bodyBuf && bodyBuf.length) {
      const namespace = sessionNamespace(resolved.id);
      const rewritten = rewriteRequestAgentId(bodyBuf, namespace);
      if (rewritten.clientAgentId !== null) {
        bodyBuf = rewritten.body;
        rewrite = { namespace, restoreTo: rewritten.clientAgentId };
      }
    }

    // Commit the memory count when the engine confirms success (2xx) and surface
    // the remaining sandbox memory budget on EVERY store response (DAK-6758), not
    // just on cap-exceeded 403s — so the playground UI can show usage during
    // normal use. On success the budget reflects the just-committed memories; on
    // a non-2xx response nothing was stored, so the budget is unchanged.
    if (storeCount > 0) {
      const origWriteHead = res.writeHead.bind(res);
      res.writeHead = (status, ...rest) => {
        let remaining = memRemainingBefore;
        if (status >= 200 && status < 300) {
          store.commitMemory(resolved.session, storeCount);
          remaining = memRemainingBefore - storeCount;
        }
        const headers = rest.length && rest[rest.length - 1] && typeof rest[rest.length - 1] === 'object'
          ? rest[rest.length - 1]
          : null;
        if (headers) headers['X-Sandbox-Memory-Remaining'] = String(Math.max(0, remaining));
        return origWriteHead(status, ...rest);
      };
    }

    forward(config, req, res, path, bodyBuf, outHeaders, rewrite);
  });
}

module.exports = { createServer, corsHeaders, countMemories };

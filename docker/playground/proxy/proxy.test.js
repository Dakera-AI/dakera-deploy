'use strict';

const test = require('node:test');
const assert = require('node:assert');
const http = require('http');
const { SessionStore } = require('./sessions');
const { isAllowed, storeKind } = require('./allowlist');
const { createServer, corsHeaders, countMemories } = require('./server');
const { sessionNamespace, rewriteRequestAgentId, restoreResponseAgentId } = require('./namespace');

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

function baseConfig(over = {}) {
  return {
    host: '127.0.0.1',
    port: 0,
    upstreamUrl: 'http://127.0.0.1:0',
    rootApiKey: 'root-secret-key',
    rateLimitPerMin: 10,
    memoryCapPerSession: 50,
    sessionTtlMs: 30 * 60 * 1000,
    maxSessionsPerIp: 20,
    maxBodyBytes: 256 * 1024,
    allowedOrigins: ['https://dakera.ai', 'https://playground.dakera.ai'],
    upstreamTimeoutMs: 5000,
    version: 'test',
    ...over,
  };
}

// Mock upstream engine: records the last request it saw, echoes a JSON body.
function startUpstream(handler) {
  const captured = [];
  const srv = http.createServer((req, res) => {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => {
      captured.push({ method: req.method, url: req.url, headers: req.headers, body: Buffer.concat(chunks).toString() });
      if (handler) return handler(req, res, captured);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ ok: true }));
    });
  });
  return new Promise((resolve) => {
    srv.listen(0, '127.0.0.1', () => resolve({ srv, captured, port: srv.address().port }));
  });
}

async function startProxy(over = {}, upstreamHandler) {
  const up = await startUpstream(upstreamHandler);
  const config = baseConfig({ upstreamUrl: `http://127.0.0.1:${up.port}`, ...over });
  const store = new SessionStore({
    rateLimitPerMin: config.rateLimitPerMin,
    memoryCap: config.memoryCapPerSession,
    ttlMs: config.sessionTtlMs,
    maxSessionsPerIp: config.maxSessionsPerIp,
  });
  const server = createServer(config, store);
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const port = server.address().port;
  return {
    port,
    upstream: up,
    store,
    close: () => new Promise((r) => server.close(() => up.srv.close(r))),
  };
}

function request(port, { method = 'GET', path = '/', headers = {}, body } = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: '127.0.0.1', port, method, path, headers }, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body: Buffer.concat(chunks).toString() }));
    });
    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
}

// ---------------------------------------------------------------------------
// unit: allow-list (req #4)
// ---------------------------------------------------------------------------

test('allow-list permits sandbox-safe endpoints', () => {
  assert.ok(isAllowed('POST', '/v1/memory/store'));
  assert.ok(isAllowed('POST', '/v1/memories/store/batch'));
  assert.ok(isAllowed('POST', '/v1/memory/recall'));
  assert.ok(isAllowed('POST', '/v1/memory/search'));
  assert.ok(isAllowed('GET', '/v1/memory/get/mem_123'));
  assert.ok(isAllowed('GET', '/v1/knowledge/query'));
  assert.ok(isAllowed('GET', '/v1/memories/mem_9/graph'));
});

// DAK-6758: the allow-list methods must match the engine route table
// (crates/api/src/lib.rs), or the proxy 403s (wrong proxy method) or the engine
// 405s (wrong engine method) — breaking playground scenarios 4 and 5.
test('allow-list methods match engine routes (DAK-6758)', () => {
  // Scenario 4 knowledge query + path: engine has GET (lib.rs:455-456).
  assert.ok(isAllowed('GET', '/v1/knowledge/query'));
  assert.ok(isAllowed('GET', '/v1/knowledge/path'));
  assert.ok(!isAllowed('POST', '/v1/knowledge/query')); // old wrong method 403'd
  assert.ok(!isAllowed('POST', '/v1/knowledge/path'));
  // Scenario 5 memory decay: engine has POST (lib.rs:400).
  assert.ok(isAllowed('POST', '/v1/memory/importance'));
  assert.ok(!isAllowed('GET', '/v1/memory/importance')); // old wrong method 405'd
  // knowledge/graph is POST-only in the engine (lib.rs:483); GET was dead.
  assert.ok(isAllowed('POST', '/v1/knowledge/graph'));
  assert.ok(!isAllowed('GET', '/v1/knowledge/graph'));
  // {id}/links is POST-only link creation (a mutation) — no read route exists,
  // so it must stay blocked by deny-by-default.
  assert.ok(!isAllowed('GET', '/v1/memories/mem_1/links'));
  assert.ok(!isAllowed('POST', '/v1/memories/mem_1/links'));
});

test('allow-list denies admin/delete/bulk/forget by default', () => {
  assert.ok(!isAllowed('POST', '/v1/memory/forget'));
  assert.ok(!isAllowed('POST', '/v1/memories/forget/batch'));
  assert.ok(!isAllowed('DELETE', '/v1/memory/get/mem_1'));
  assert.ok(!isAllowed('GET', '/admin/cluster/status'));
  assert.ok(!isAllowed('POST', '/admin/cache/clear'));
  assert.ok(!isAllowed('DELETE', '/v1/namespaces/ns/vectors/bulk-delete'));
  assert.ok(!isAllowed('POST', '/v1/export'));
  assert.ok(!isAllowed('POST', '/v1/import'));
  assert.ok(!isAllowed('PUT', '/v1/memory/update/mem_1'));
});

test('storeKind classifies store endpoints', () => {
  assert.equal(storeKind('POST', '/v1/memory/store'), 'single');
  assert.equal(storeKind('POST', '/v1/memories/store/batch'), 'batch');
  assert.equal(storeKind('POST', '/v1/memory/recall'), 'none');
});

test('countMemories handles single, batch shapes, and bad json', () => {
  assert.equal(countMemories('single', Buffer.from('{}')), 1);
  assert.equal(countMemories('batch', Buffer.from(JSON.stringify({ memories: [1, 2, 3] }))), 3);
  assert.equal(countMemories('batch', Buffer.from(JSON.stringify([1, 2]))), 2);
  assert.equal(countMemories('batch', Buffer.from('not json')), 1);
});

// ---------------------------------------------------------------------------
// unit: session store (req #1, #2, #3)
// ---------------------------------------------------------------------------

test('rate limit allows N then blocks within the window (req #1)', () => {
  let now = 1_000_000;
  const store = new SessionStore({ rateLimitPerMin: 3, memoryCap: 50, ttlMs: 1e9, maxSessionsPerIp: 0, now: () => now });
  const { session } = store.resolve('pg_abcdefgh', '1.1.1.1');
  assert.ok(store.checkRate(session).ok);
  assert.ok(store.checkRate(session).ok);
  assert.ok(store.checkRate(session).ok);
  const blocked = store.checkRate(session);
  assert.equal(blocked.ok, false);
  assert.ok(blocked.retryAfterSec >= 1);
  now += 61_000; // window slides past
  assert.ok(store.checkRate(session).ok);
});

test('memory cap blocks once exceeded (req #2)', () => {
  const store = new SessionStore({ rateLimitPerMin: 1000, memoryCap: 3, ttlMs: 1e9, maxSessionsPerIp: 0 });
  const { session } = store.resolve('pg_abcdefgh', '1.1.1.1');
  assert.ok(store.checkMemoryCap(session, 2).ok);
  store.commitMemory(session, 2);
  assert.ok(store.checkMemoryCap(session, 1).ok);
  store.commitMemory(session, 1);
  assert.equal(store.checkMemoryCap(session, 1).ok, false); // 3/3 used
  // a batch larger than remaining is rejected wholesale
  const store2 = new SessionStore({ rateLimitPerMin: 1000, memoryCap: 3, ttlMs: 1e9, maxSessionsPerIp: 0 });
  const s2 = store2.resolve('pg_batch123', '2.2.2.2').session;
  assert.equal(store2.checkMemoryCap(s2, 5).ok, false);
});

test('session expires after TTL and resets state (req #3)', () => {
  let now = 0;
  const store = new SessionStore({ rateLimitPerMin: 1000, memoryCap: 50, ttlMs: 1000, maxSessionsPerIp: 0, now: () => now });
  const first = store.resolve('pg_session1', '3.3.3.3');
  store.commitMemory(first.session, 10);
  assert.equal(first.session.memoryCount, 10);
  now = 1001; // past TTL
  const second = store.resolve('pg_session1', '3.3.3.3');
  assert.equal(second.session.memoryCount, 0); // fresh state
  assert.equal(store.sweep === store.sweep, true);
});

test('per-IP session ceiling bounds header rotation', () => {
  const store = new SessionStore({ rateLimitPerMin: 1000, memoryCap: 50, ttlMs: 1e9, maxSessionsPerIp: 2 });
  assert.ok(store.resolve('pg_aaaaaaaa', '9.9.9.9').ok);
  assert.ok(store.resolve('pg_bbbbbbbb', '9.9.9.9').ok);
  const third = store.resolve('pg_cccccccc', '9.9.9.9');
  assert.equal(third.ok, false);
  assert.equal(third.code, 429);
});

test('sweep removes expired sessions', () => {
  let now = 0;
  const store = new SessionStore({ rateLimitPerMin: 10, memoryCap: 50, ttlMs: 100, maxSessionsPerIp: 0, now: () => now });
  store.resolve('pg_keepalive', '4.4.4.4');
  assert.equal(store.size, 1);
  now = 200;
  assert.equal(store.sweep(), 1);
  assert.equal(store.size, 0);
});

// ---------------------------------------------------------------------------
// unit: CORS (req #5)
// ---------------------------------------------------------------------------

test('CORS reflects allowed origin only', () => {
  const cfg = baseConfig();
  assert.equal(corsHeaders(cfg, 'https://dakera.ai')['Access-Control-Allow-Origin'], 'https://dakera.ai');
  assert.equal(corsHeaders(cfg, 'https://evil.com')['Access-Control-Allow-Origin'], undefined);
});

// ---------------------------------------------------------------------------
// integration: full request pipeline
// ---------------------------------------------------------------------------

test('health endpoint returns 200 and is not forwarded (req #6)', async () => {
  const p = await startProxy();
  const res = await request(p.port, { path: '/health' });
  assert.equal(res.status, 200);
  const json = JSON.parse(res.body);
  assert.equal(json.status, 'ok');
  assert.equal(p.upstream.captured.length, 0);
  await p.close();
});

test('CORS preflight answered with 204, never forwarded (req #5)', async () => {
  const p = await startProxy();
  const res = await request(p.port, { method: 'OPTIONS', path: '/v1/memory/store', headers: { origin: 'https://dakera.ai' } });
  assert.equal(res.status, 204);
  assert.equal(res.headers['access-control-allow-origin'], 'https://dakera.ai');
  assert.equal(p.upstream.captured.length, 0);
  await p.close();
});

test('allowed store forwards, injects root key, strips client creds (req #4 + auth)', async () => {
  const p = await startProxy();
  const res = await request(p.port, {
    method: 'POST',
    path: '/v1/memory/store',
    headers: { 'content-type': 'application/json', authorization: 'Bearer playground-demo', origin: 'https://dakera.ai' },
    body: JSON.stringify({ agent_id: 'demo', content: 'hello' }),
  });
  assert.equal(res.status, 200);
  assert.ok(res.headers['x-playground-session']); // session minted
  assert.equal(res.headers['access-control-allow-origin'], 'https://dakera.ai');
  const seen = p.upstream.captured[0];
  assert.equal(seen.headers.authorization, 'Bearer root-secret-key'); // injected
  assert.notEqual(seen.headers.authorization, 'Bearer playground-demo'); // stripped
  await p.close();
});

test('denied admin endpoint returns 403 and is not forwarded (req #4)', async () => {
  const p = await startProxy();
  const res = await request(p.port, { method: 'GET', path: '/admin/cache/clear' });
  assert.equal(res.status, 403);
  assert.equal(JSON.parse(res.body).error, 'forbidden_endpoint');
  assert.equal(p.upstream.captured.length, 0);
  await p.close();
});

test('forget (delete) endpoint blocked (req #4)', async () => {
  const p = await startProxy();
  const res = await request(p.port, { method: 'POST', path: '/v1/memory/forget', body: '{}', headers: { 'content-type': 'application/json' } });
  assert.equal(res.status, 403);
  assert.equal(p.upstream.captured.length, 0);
  await p.close();
});

test('rate limit returns 429 after the per-session budget (req #1)', async () => {
  const p = await startProxy({ rateLimitPerMin: 3 });
  const headers = { 'content-type': 'application/json' };
  const sess = 'pg_ratetest1';
  for (let i = 0; i < 3; i++) {
    const r = await request(p.port, { method: 'POST', path: '/v1/memory/recall', headers: { ...headers, 'x-playground-session': sess }, body: '{}' });
    assert.equal(r.status, 200);
  }
  const blocked = await request(p.port, { method: 'POST', path: '/v1/memory/recall', headers: { ...headers, 'x-playground-session': sess }, body: '{}' });
  assert.equal(blocked.status, 429);
  assert.ok(Number(blocked.headers['retry-after']) >= 1);
  await p.close();
});

test('memory cap returns 403 once reached (req #2)', async () => {
  const p = await startProxy({ rateLimitPerMin: 1000, memoryCapPerSession: 2 });
  const headers = { 'content-type': 'application/json', 'x-playground-session': 'pg_captest1' };
  for (let i = 0; i < 2; i++) {
    const r = await request(p.port, { method: 'POST', path: '/v1/memory/store', headers, body: JSON.stringify({ content: `m${i}` }) });
    assert.equal(r.status, 200);
  }
  const capped = await request(p.port, { method: 'POST', path: '/v1/memory/store', headers, body: JSON.stringify({ content: 'overflow' }) });
  assert.equal(capped.status, 403);
  assert.equal(JSON.parse(capped.body).error, 'memory_cap_reached');
  assert.equal(p.upstream.captured.length, 2); // overflow never forwarded
  await p.close();
});

test('batch store counts items against the cap (req #2)', async () => {
  const p = await startProxy({ rateLimitPerMin: 1000, memoryCapPerSession: 5 });
  const headers = { 'content-type': 'application/json', 'x-playground-session': 'pg_batchcap' };
  const r1 = await request(p.port, { method: 'POST', path: '/v1/memories/store/batch', headers, body: JSON.stringify({ memories: [1, 2, 3] }) });
  assert.equal(r1.status, 200);
  const r2 = await request(p.port, { method: 'POST', path: '/v1/memories/store/batch', headers, body: JSON.stringify({ memories: [1, 2, 3] }) });
  assert.equal(r2.status, 403); // 3 + 3 > 5
  await p.close();
});

test('oversized body rejected with 413', async () => {
  const p = await startProxy({ maxBodyBytes: 64 });
  const res = await request(p.port, {
    method: 'POST',
    path: '/v1/memory/store',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ content: 'x'.repeat(500) }),
  });
  assert.equal(res.status, 413);
  await p.close();
});

test('non-2xx store response does not consume the memory cap', async () => {
  const p = await startProxy({ memoryCapPerSession: 1 }, (req, res) => {
    res.writeHead(400, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'bad' }));
  });
  const headers = { 'content-type': 'application/json', 'x-playground-session': 'pg_failtest' };
  const r1 = await request(p.port, { method: 'POST', path: '/v1/memory/store', headers, body: '{}' });
  assert.equal(r1.status, 400);
  // cap not consumed → a second (succeeding shape) request still allowed by cap
  const sess = p.store.resolve('pg_failtest', '127.0.0.1').session;
  assert.equal(sess.memoryCount, 0);
  await p.close();
});

// DAK-6758: the remaining sandbox memory budget must be surfaced on every store
// response (success too), not only on the cap-exceeded 403, so the playground UI
// can show usage during normal stores.
test('successful store returns X-Sandbox-Memory-Remaining (DAK-6758)', async () => {
  const p = await startProxy({ rateLimitPerMin: 1000, memoryCapPerSession: 50 });
  const headers = { 'content-type': 'application/json', 'x-playground-session': 'pg_remaintest' };
  const r1 = await request(p.port, { method: 'POST', path: '/v1/memory/store', headers, body: JSON.stringify({ content: 'a' }) });
  assert.equal(r1.status, 200);
  assert.equal(r1.headers['x-sandbox-memory-remaining'], '49'); // 50 - 1 committed
  const r2 = await request(p.port, { method: 'POST', path: '/v1/memories/store/batch', headers, body: JSON.stringify({ memories: [1, 2, 3] }) });
  assert.equal(r2.status, 200);
  assert.equal(r2.headers['x-sandbox-memory-remaining'], '46'); // 49 - 3 committed
  await p.close();
});

test('failed store reports unchanged X-Sandbox-Memory-Remaining (DAK-6758)', async () => {
  const p = await startProxy({ rateLimitPerMin: 1000, memoryCapPerSession: 10 }, (req, res) => {
    res.writeHead(400, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'bad' }));
  });
  const headers = { 'content-type': 'application/json', 'x-playground-session': 'pg_remainfail' };
  const r = await request(p.port, { method: 'POST', path: '/v1/memory/store', headers, body: '{}' });
  assert.equal(r.status, 400);
  assert.equal(r.headers['x-sandbox-memory-remaining'], '10'); // nothing stored → budget intact
  await p.close();
});

// ---------------------------------------------------------------------------
// unit: per-session agent_id namespacing (DAK-6757)
// ---------------------------------------------------------------------------

test('sessionNamespace is deterministic, prefixed, and per-session unique (DAK-6757)', () => {
  const a = sessionNamespace('pg_abcdefgh');
  const b = sessionNamespace('pg_abcdefgh');
  const c = sessionNamespace('pg_zzzzzzzz');
  assert.equal(a, b); // deterministic — a session can recall its own stores
  assert.notEqual(a, c); // different sessions -> different namespaces
  assert.match(a, /^playground-demo-[0-9a-f]{12}$/);
});

test('rewriteRequestAgentId rewrites top-level + nested and captures original (DAK-6757)', () => {
  const ns = sessionNamespace('pg_session1');
  const r = rewriteRequestAgentId(
    Buffer.from(JSON.stringify({ agent_id: 'playground-demo', memories: [{ agent_id: 'playground-demo', content: 'x' }, { content: 'y' }] })),
    ns,
  );
  const parsed = JSON.parse(r.body.toString());
  assert.equal(parsed.agent_id, ns); // top-level rewritten
  assert.equal(parsed.memories[0].agent_id, ns); // nested rewritten when present
  assert.equal(parsed.memories[1].agent_id, undefined); // nested without agent_id inherits top-level
  assert.equal(r.clientAgentId, 'playground-demo');
});

test('rewriteRequestAgentId forces namespace when agent_id omitted (DAK-6757)', () => {
  const ns = sessionNamespace('pg_session2');
  const r = rewriteRequestAgentId(Buffer.from(JSON.stringify({ query: 'bank account' })), ns);
  assert.equal(JSON.parse(r.body.toString()).agent_id, ns); // forced — cannot fall back to shared default
  assert.equal(r.clientAgentId, 'playground-demo'); // restore to public placeholder
});

test('rewriteRequestAgentId leaves non-JSON and custom agent_id intact (DAK-6757)', () => {
  const ns = sessionNamespace('pg_session3');
  const bad = rewriteRequestAgentId(Buffer.from('not json'), ns);
  assert.equal(bad.body.toString(), 'not json');
  assert.equal(bad.clientAgentId, null); // not rewritten
  const custom = rewriteRequestAgentId(Buffer.from(JSON.stringify({ agent_id: 'demo', content: 'z' })), ns);
  assert.equal(custom.clientAgentId, 'demo'); // original preserved for response restore
});

test('restoreResponseAgentId swaps the namespace back to the client value (DAK-6757)', () => {
  const ns = sessionNamespace('pg_session4');
  const body = Buffer.from(JSON.stringify({ agent_id: ns, results: [`${ns} stored`] }));
  const restored = JSON.parse(restoreResponseAgentId(body, ns, 'playground-demo').toString());
  assert.equal(restored.agent_id, 'playground-demo');
  assert.equal(restored.results[0], 'playground-demo stored'); // every occurrence swapped
  // unrelated body untouched
  const plain = Buffer.from('{"ok":true}');
  assert.equal(restoreResponseAgentId(plain, ns, 'playground-demo').toString(), '{"ok":true}');
});

// ---------------------------------------------------------------------------
// integration: cross-session isolation end-to-end (DAK-6757 acceptance)
// ---------------------------------------------------------------------------

// Stateful mock engine: a per-agent_id memory store, mirroring how the real
// engine isolates by agent_id. Lets us prove a session cannot read another's.
function memoryEngine() {
  const byAgent = new Map();
  return (req, res, captured) => {
    let parsed = {};
    try {
      parsed = JSON.parse(captured[captured.length - 1].body);
    } catch {
      /* ignore */
    }
    const agent = parsed.agent_id || 'default';
    res.writeHead(200, { 'Content-Type': 'application/json' });
    if (req.url.includes('/store')) {
      const arr = byAgent.get(agent) || [];
      arr.push(parsed.content);
      byAgent.set(agent, arr);
      res.end(JSON.stringify({ ok: true, agent_id: agent }));
    } else if (req.url.includes('/recall')) {
      res.end(JSON.stringify({ agent_id: agent, results: byAgent.get(agent) || [] }));
    } else {
      res.end(JSON.stringify({ agent_id: agent }));
    }
  };
}

function storeReq(port, session, content) {
  return request(port, {
    method: 'POST',
    path: '/v1/memory/store',
    headers: { 'content-type': 'application/json', 'x-playground-session': session },
    body: JSON.stringify({ agent_id: 'playground-demo', content }),
  });
}

function recallReq(port, session, query) {
  return request(port, {
    method: 'POST',
    path: '/v1/memory/recall',
    headers: { 'content-type': 'application/json', 'x-playground-session': session },
    body: JSON.stringify({ agent_id: 'playground-demo', query }),
  });
}

test('a fresh session cannot recall another session PII (DAK-6757 AC#1)', async () => {
  const p = await startProxy({ rateLimitPerMin: 1000 }, memoryEngine());
  await storeReq(p.port, 'pg_sessionAAA1', 'Alice Chen is a software engineer');
  await storeReq(p.port, 'pg_sessionBBB1', 'SECRET bank account 1234-5678-9012');

  // Session C — brand new — tries to recall the bank account.
  const c = await recallReq(p.port, 'pg_sessionCCC1', 'bank account');
  const cj = JSON.parse(c.body);
  assert.deepEqual(cj.results, []); // isolated — sees nothing from A or B
  assert.equal(cj.agent_id, 'playground-demo'); // response restored, no namespace leak

  // Session B can still recall its OWN memory (deterministic namespace).
  const b = await recallReq(p.port, 'pg_sessionBBB1', 'bank account');
  assert.deepEqual(JSON.parse(b.body).results, ['SECRET bank account 1234-5678-9012']);
  await p.close();
});

test('agent_id is namespaced per session before forwarding (DAK-6757)', async () => {
  const p = await startProxy({ rateLimitPerMin: 1000 });
  await storeReq(p.port, 'pg_nsOne0001', 'hello one');
  await storeReq(p.port, 'pg_nsTwo0002', 'hello two');
  const a1 = JSON.parse(p.upstream.captured[0].body).agent_id;
  const a2 = JSON.parse(p.upstream.captured[1].body).agent_id;
  assert.notEqual(a1, 'playground-demo'); // client value never reaches the engine verbatim
  assert.ok(a1.startsWith('playground-demo-'));
  assert.notEqual(a1, a2); // distinct sessions -> distinct engine namespaces
  await p.close();
});

test('header-less clients are isolated by IP bucket namespace (DAK-6757)', async () => {
  const p = await startProxy({ rateLimitPerMin: 1000 }, memoryEngine());
  // No X-Playground-Session header -> falls back to ip: bucket; still namespaced.
  const store = await request(p.port, {
    method: 'POST',
    path: '/v1/memory/store',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ agent_id: 'playground-demo', content: 'ip-bucket secret' }),
  });
  assert.equal(store.status, 200);
  const seen = JSON.parse(p.upstream.captured[0].body).agent_id;
  assert.ok(seen.startsWith('playground-demo-'));
  assert.notEqual(seen, 'playground-demo');
  await p.close();
});

test('batch store namespaces every item against the session (DAK-6757)', async () => {
  const p = await startProxy({ rateLimitPerMin: 1000, memoryCapPerSession: 50 });
  const ns = sessionNamespace('pg_batchns01');
  const res = await request(p.port, {
    method: 'POST',
    path: '/v1/memories/store/batch',
    headers: { 'content-type': 'application/json', 'x-playground-session': 'pg_batchns01' },
    body: JSON.stringify({ agent_id: 'playground-demo', memories: [{ agent_id: 'playground-demo', content: 'a' }, { content: 'b' }] }),
  });
  assert.equal(res.status, 200);
  const body = JSON.parse(p.upstream.captured[0].body);
  assert.equal(body.agent_id, ns);
  assert.equal(body.memories[0].agent_id, ns); // per-item agent_id rewritten too
  await p.close();
});

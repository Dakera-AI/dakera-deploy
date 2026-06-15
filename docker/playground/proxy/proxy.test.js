'use strict';

const test = require('node:test');
const assert = require('node:assert');
const http = require('http');
const { SessionStore } = require('./sessions');
const { isAllowed, storeKind } = require('./allowlist');
const { createServer, corsHeaders, countMemories } = require('./server');

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
  assert.ok(isAllowed('POST', '/v1/knowledge/query'));
  assert.ok(isAllowed('GET', '/v1/memories/mem_9/graph'));
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

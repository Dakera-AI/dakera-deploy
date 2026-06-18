'use strict';

const http = require('http');
const { config } = require('./config');
const { createServer } = require('./server');
const { SessionStore } = require('./sessions');
const { NS_PREFIX } = require('./namespace');

// =============================================================================
// Entrypoint — wires config + session store + HTTP server and starts listening.
// =============================================================================

function deleteNamespace(ns) {
  const url = new URL(config.upstreamUrl + '/v1/namespaces/' + encodeURIComponent(ns));
  const headers = { 'Content-Type': 'application/json' };
  if (config.rootApiKey) headers['authorization'] = `Bearer ${config.rootApiKey}`;

  const req = http.request({
    protocol: url.protocol,
    hostname: url.hostname,
    port: url.port || 80,
    method: 'DELETE',
    path: url.pathname,
    headers,
    timeout: 10000,
  });
  req.on('error', () => {});
  req.on('timeout', () => req.destroy());
  req.end();
}

function purgeStaleNamespaces() {
  const url = new URL(config.upstreamUrl + '/v1/namespaces');
  const headers = { 'Content-Type': 'application/json' };
  if (config.rootApiKey) headers['authorization'] = `Bearer ${config.rootApiKey}`;

  const req = http.request({
    protocol: url.protocol,
    hostname: url.hostname,
    port: url.port || 80,
    method: 'GET',
    path: url.pathname,
    headers,
    timeout: 15000,
  }, (res) => {
    const chunks = [];
    res.on('data', (c) => chunks.push(c));
    res.on('end', () => {
      try {
        const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
        const nsList = Array.isArray(body) ? body : (body.namespaces || []);
        const prefix = '_dakera_agent_' + NS_PREFIX + '-';
        let purged = 0;
        for (const entry of nsList) {
          const name = typeof entry === 'string' ? entry : (entry.name || entry.id || '');
          if (name.startsWith(prefix)) {
            deleteNamespace(name);
            purged++;
          }
        }
        if (purged > 0) {
          console.log(`[sandbox-proxy] startup purge: deleting ${purged} stale playground namespace(s)`);
        }
      } catch (_) {}
    });
  });
  req.on('error', (e) => {
    console.warn(`[sandbox-proxy] startup purge failed: ${e.message}`);
  });
  req.on('timeout', () => req.destroy());
  req.end();
}

function main() {
  if (!config.rootApiKey) {
    console.warn(
      '[sandbox-proxy] WARNING: DAKERA_ROOT_API_KEY is not set — forwarded requests will be unauthenticated.',
    );
  }

  const store = new SessionStore({
    rateLimitPerMin: config.rateLimitPerMin,
    memoryCap: config.memoryCapPerSession,
    ttlMs: config.sessionTtlMs,
    maxSessionsPerIp: config.maxSessionsPerIp,
    llmRateLimit: config.llmRateLimitPer10Min,
    onExpire: (_sessionId, session) => {
      if (!session.namespaces) return;
      for (const ns of session.namespaces) {
        deleteNamespace('_dakera_agent_' + ns);
        console.log(`[sandbox-proxy] expired session — deleting namespace ${ns}`);
      }
    },
  });

  const sweep = setInterval(() => {
    const removed = store.sweep();
    if (removed > 0) console.log(`[sandbox-proxy] swept ${removed} expired session(s)`);
  }, config.sweepIntervalMs);
  sweep.unref();

  const server = createServer(config, store);
  server.listen(config.port, config.host, () => {
    console.log(
      `[sandbox-proxy] v${config.version} listening on ${config.host}:${config.port} -> ${config.upstreamUrl} ` +
        `| rate=${config.rateLimitPerMin}/min cap=${config.memoryCapPerSession} ttl=${config.sessionTtlMs / 1000}s`,
    );
    // BUG 6: Purge historical playground namespaces on startup
    setTimeout(() => purgeStaleNamespaces(), 2000);
  });

  const shutdown = (sig) => {
    console.log(`[sandbox-proxy] ${sig} received — shutting down`);
    clearInterval(sweep);
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 5000).unref();
  };
  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));
}

main();

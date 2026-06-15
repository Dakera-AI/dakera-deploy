'use strict';

const { config } = require('./config');
const { createServer } = require('./server');
const { SessionStore } = require('./sessions');

// =============================================================================
// Entrypoint — wires config + session store + HTTP server and starts listening.
// =============================================================================

function main() {
  if (!config.rootApiKey) {
    // Fail loud rather than silently forwarding unauthenticated requests to an
    // auth-enabled engine (would produce confusing upstream 401s).
    console.warn(
      '[sandbox-proxy] WARNING: DAKERA_ROOT_API_KEY is not set — forwarded requests will be unauthenticated.',
    );
  }

  const store = new SessionStore({
    rateLimitPerMin: config.rateLimitPerMin,
    memoryCap: config.memoryCapPerSession,
    ttlMs: config.sessionTtlMs,
    maxSessionsPerIp: config.maxSessionsPerIp,
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

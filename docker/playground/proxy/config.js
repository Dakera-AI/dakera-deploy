'use strict';

// =============================================================================
// Dakera Playground Sandbox Proxy — configuration (DAK-6713)
// =============================================================================
// All knobs are env-driven with sandbox-safe defaults so the proxy is fully
// configurable from docker-compose without a rebuild. Defaults match the
// acceptance criteria in DAK-6713.
// =============================================================================

function intEnv(name, fallback) {
  const raw = process.env[name];
  if (raw === undefined || raw === '') return fallback;
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n) || n < 0) {
    throw new Error(`Invalid integer for ${name}: ${JSON.stringify(raw)}`);
  }
  return n;
}

function listEnv(name, fallback) {
  const raw = process.env[name];
  if (raw === undefined || raw === '') return fallback;
  return raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}

const config = {
  // Network
  host: process.env.PROXY_HOST || '0.0.0.0',
  port: intEnv('PROXY_PORT', 3100),

  // Upstream Dakera engine (inside the playground docker network)
  upstreamUrl: (process.env.DAKERA_UPSTREAM_URL || 'http://dakera:3000').replace(/\/+$/, ''),

  // Server-side root key injected on every forwarded request. Clients never
  // see or send this — they authenticate with the public "playground-demo"
  // placeholder. Required when the upstream has DAKERA_AUTH_ENABLED=true.
  rootApiKey: process.env.DAKERA_ROOT_API_KEY || '',

  // Sandbox limits (DAK-6713 acceptance criteria)
  rateLimitPerMin: intEnv('SANDBOX_RATE_LIMIT_PER_MIN', 30), // req #1
  memoryCapPerSession: intEnv('SANDBOX_MEMORY_CAP', 50), //      req #2
  sessionTtlMs: intEnv('SANDBOX_SESSION_TTL_SEC', 30 * 60) * 1000, // req #3

  // Defence-in-depth: bound how many distinct sandbox sessions a single IP can
  // hold at once so the per-session caps cannot be trivially bypassed by
  // rotating the session header. Nginx still applies the per-IP req/s ceiling.
  maxSessionsPerIp: intEnv('SANDBOX_MAX_SESSIONS_PER_IP', 20),

  // Reject oversized request bodies before they reach the engine. The engine
  // itself allows 5 MB; the sandbox keeps demo payloads small.
  maxBodyBytes: intEnv('SANDBOX_MAX_BODY_BYTES', 256 * 1024),

  // CORS — the playground page is served from dakera.ai and calls the backend
  // at playground.dakera.ai/v1 (cross-origin). Allow both plus www. (req #5)
  allowedOrigins: listEnv('SANDBOX_ALLOWED_ORIGINS', [
    'https://dakera.ai',
    'https://www.dakera.ai',
    'https://playground.dakera.ai',
  ]),

  // Upstream call timeout (matches engine DAKERA_REQUEST_TIMEOUT default)
  upstreamTimeoutMs: intEnv('SANDBOX_UPSTREAM_TIMEOUT_SEC', 30) * 1000,

  // How often to sweep expired sessions out of memory.
  sweepIntervalMs: intEnv('SANDBOX_SWEEP_INTERVAL_SEC', 60) * 1000,

  // LLM comparison endpoint (DAK-6845) — OpenRouter free-model side-by-side.
  openRouterApiKey: process.env.OPENROUTER_API_KEY || '',
  llmCompareTimeoutMs: intEnv('LLM_COMPARE_TIMEOUT_SEC', 30) * 1000,
  llmRateLimitPer10Min: intEnv('SANDBOX_LLM_RATE_LIMIT', 5),

  version: process.env.PROXY_VERSION || 'dak6713-1',
};

module.exports = { config, intEnv, listEnv };

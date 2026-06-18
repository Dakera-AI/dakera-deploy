'use strict';

const crypto = require('crypto');

// =============================================================================
// Sandbox session store (DAK-6713 req #1, #2, #3) — in-memory, TTL-bounded.
// =============================================================================
// A session is identified by the `X-Playground-Session` header. When a client
// does not present a valid one (no header or non-pg_ value), a fresh pg_xxx
// session is minted and returned via X-Playground-Session so the client can
// reuse it on subsequent requests. This guarantees every client gets a unique
// namespace for memory isolation (DAK-6757/DAK-6783). A per-IP cap on the
// number of live sessions bounds header-rotation abuse.
//
// All time is injected via a `now()` clock so the logic is deterministic under
// test.
// =============================================================================

const SESSION_RE = /^pg_[A-Za-z0-9_-]{8,64}$/;

function newSessionId() {
  return 'pg_' + crypto.randomBytes(18).toString('base64url');
}

class SessionStore {
  /**
   * @param {object} opts
   * @param {number} opts.rateLimitPerMin
   * @param {number} opts.memoryCap
   * @param {number} opts.ttlMs
   * @param {number} opts.maxSessionsPerIp
   * @param {number} [opts.llmRateLimit]  – max LLM compare calls per 10 min (DAK-6845)
   * @param {() => number} [opts.now]
   */
  constructor(opts) {
    this.rateLimitPerMin = opts.rateLimitPerMin;
    this.memoryCap = opts.memoryCap;
    this.ttlMs = opts.ttlMs;
    this.maxSessionsPerIp = opts.maxSessionsPerIp;
    this.llmRateLimit = opts.llmRateLimit !== undefined ? opts.llmRateLimit : 5;
    this.now = opts.now || Date.now;
    this.onExpire = opts.onExpire || null;
    /** @type {Map<string, {createdAt:number, calls:number[], memoryCount:number, ip:string, generated:boolean, llmCalls?:number[], llmSeeded?:boolean, namespaces?:Set<string>}>} */
    this.sessions = new Map();
  }

  _expired(s) {
    return this.now() - s.createdAt > this.ttlMs;
  }

  /**
   * Resolve the session for a request, creating one if needed.
   * @returns {{ok:true, id:string, generated:boolean, session:object}
   *          |{ok:false, code:number, error:string, message:string}}
   */
  resolve(headerValue, ip) {
    const hdr = typeof headerValue === 'string' ? headerValue.trim() : '';
    const provided = SESSION_RE.test(hdr);
    // For clients with a valid pg_xxx header, use it as the key.
    // For clients without a valid header, look up any existing legacy ip:-keyed
    // session so in-flight requests aren't orphaned (DAK-6783).
    const key = provided ? hdr : `ip:${ip || 'unknown'}`;

    let s = this.sessions.get(key);
    if (s && this._expired(s)) {
      // req #3: 30-min auto-expiry — drop stale state, start fresh.
      if (this.onExpire && s.namespaces && s.namespaces.size > 0) {
        try { this.onExpire(key, s); } catch (_) {}
      }
      this.sessions.delete(key);
      s = undefined;
    }

    if (!s) {
      // Enforce per-IP live-session ceiling before minting a new session.
      if (this.maxSessionsPerIp > 0 && this._liveSessionsForIp(ip) >= this.maxSessionsPerIp) {
        return {
          ok: false,
          code: 429,
          error: 'too_many_sessions',
          message: `Too many active sandbox sessions from this address (max ${this.maxSessionsPerIp}). Try again later.`,
        };
      }
      // Mint a fresh pg_xxx session ID for new sessions — both for clients that
      // provided no header AND for IP-fallback clients. Returning a pg_xxx ID
      // via X-Playground-Session lets the client reuse it on subsequent requests,
      // giving every client a unique engine namespace (DAK-6757/DAK-6783).
      const mintedId = provided ? hdr : newSessionId();
      s = { createdAt: this.now(), calls: [], memoryCount: 0, ip: ip || 'unknown', generated: !provided };
      this.sessions.set(mintedId, s);
      return { ok: true, id: mintedId, generated: !provided, session: s };
    }

    // Existing session: for pg_xxx clients return their key; for legacy ip:-keyed
    // sessions return the key too (they expire within 30 min and get pg_xxx after).
    return { ok: true, id: provided ? hdr : key, generated: !provided, session: s };
  }

  _liveSessionsForIp(ip) {
    let n = 0;
    for (const s of this.sessions.values()) {
      if (s.ip === ip && !this._expired(s)) n += 1;
    }
    return n;
  }

  /**
   * req #1: sliding 60s window rate limit. Records the call when allowed.
   * @returns {{ok:true, remaining:number}|{ok:false, retryAfterSec:number}}
   */
  checkRate(session) {
    const now = this.now();
    const windowStart = now - 60_000;
    session.calls = session.calls.filter((t) => t > windowStart);
    if (session.calls.length >= this.rateLimitPerMin) {
      const oldest = session.calls[0];
      const retryAfterSec = Math.max(1, Math.ceil((oldest + 60_000 - now) / 1000));
      return { ok: false, retryAfterSec };
    }
    session.calls.push(now);
    return { ok: true, remaining: this.rateLimitPerMin - session.calls.length };
  }

  /**
   * req #2: would storing `count` more memories exceed the cap?
   * @returns {{ok:true, remaining:number}|{ok:false, remaining:number}}
   */
  checkMemoryCap(session, count) {
    const remaining = this.memoryCap - session.memoryCount;
    if (count > remaining) return { ok: false, remaining };
    return { ok: true, remaining };
  }

  /** Commit a successful store of `count` memories. */
  commitMemory(session, count) {
    session.memoryCount += count;
  }

  /**
   * LLM-specific rate limit (DAK-6845): sliding 10-min window.
   * Called only on POST /v1/playground/llm-compare requests.
   * Records the call when allowed.
   * @returns {{ok:true, remaining:number}|{ok:false, retryAfterSec:number}}
   */
  checkLlmRate(session) {
    const now = this.now();
    const windowStart = now - 10 * 60_000;
    session.llmCalls = (session.llmCalls || []).filter((t) => t > windowStart);
    if (session.llmCalls.length >= this.llmRateLimit) {
      const oldest = session.llmCalls[0];
      const retryAfterSec = Math.max(1, Math.ceil((oldest + 10 * 60_000 - now) / 1000));
      return { ok: false, retryAfterSec };
    }
    session.llmCalls.push(now);
    return { ok: true, remaining: this.llmRateLimit - session.llmCalls.length };
  }

  /** Track a namespace used by this session (for cleanup on expiry). */
  trackNamespace(session, namespace) {
    if (!session.namespaces) session.namespaces = new Set();
    session.namespaces.add(namespace);
  }

  /** Evict expired sessions; calls onExpire for engine cleanup. Returns count removed. */
  sweep() {
    let removed = 0;
    for (const [k, s] of this.sessions) {
      if (this._expired(s)) {
        if (this.onExpire && s.namespaces && s.namespaces.size > 0) {
          try { this.onExpire(k, s); } catch (_) {}
        }
        this.sessions.delete(k);
        removed += 1;
      }
    }
    return removed;
  }

  get size() {
    return this.sessions.size;
  }
}

module.exports = { SessionStore, newSessionId, SESSION_RE };

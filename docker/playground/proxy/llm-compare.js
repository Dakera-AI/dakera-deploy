'use strict';

// =============================================================================
// LLM side-by-side comparison handler (DAK-6845)
// =============================================================================
// Implements POST /v1/playground/llm-compare: calls the same free OpenRouter
// model twice in parallel — once with no context (raw question) and once with
// relevant Dakera memories injected as a system prompt — so users can see what
// memory-augmented AI looks like vs. a plain LLM.
//
// Internalfunctions are exported individually so unit tests can inject mocks
// via the opts._callXxx pattern without patching require() globals.
// =============================================================================

const https = require('https');
const http = require('http');
const { URL } = require('url');
const { sessionNamespace } = require('./namespace');

// Seed memories covering medical, engineering, legal, and financial domains.
// Stored into the session namespace on the FIRST llm-compare call so that
// "with memory" immediately shows a meaningful improvement over "without".
const SEED_MEMORIES = [
  // Medical
  {
    content:
      'Patient John Smith (DOB: 1978-03-15) is currently taking Metformin 500mg twice daily and Lisinopril 10mg once daily for Type 2 diabetes and hypertension. Next review: 2026-09-01.',
    importance: 0.9,
  },
  {
    content:
      'Patient Sarah Johnson has a documented penicillin allergy causing anaphylaxis. Alternative antibiotics on file: azithromycin or clindamycin. Allergy flagged across all records.',
    importance: 0.9,
  },
  {
    content:
      "Dr. Martinez noted that patient Maria Garcia's HbA1c improved from 9.2% to 7.4% after switching to insulin glargine in January 2026. Follow-up: 2026-07-15.",
    importance: 0.8,
  },
  // Engineering
  {
    content:
      'The API gateway uses a Redis cluster with 3 nodes: primary at 10.0.1.50:6379, replicas at 10.0.1.51 and 10.0.1.52. Failover timeout 5 s, max connections per node: 500.',
    importance: 0.85,
  },
  {
    content:
      'The deployment pipeline uses blue-green strategy. Health-check window: 10 minutes. Auto-rollback triggers if error rate exceeds 1% in the first 30 minutes post-deploy.',
    importance: 0.85,
  },
  // Legal
  {
    content:
      'Contract #2026-ACME-0042 with ACME Corp expires 2026-12-31. Terms: 90-day termination notice, $50,000 early-exit penalty, auto-renewal unless cancelled 60 days before expiry.',
    importance: 0.9,
  },
  {
    content:
      'Rodriguez & Associates signed NDA on 2026-01-15 covering all product roadmap discussions and unreleased pricing. NDA expires 2029-01-15. Liquidated damages: $250,000.',
    importance: 0.9,
  },
  // Financial
  {
    content:
      'Q1 2026 budget: Engineering $2.4M, Marketing $800K, Sales $1.2M, Operations $600K. Total $5.0M approved. YTD burn as of March: $1.1M (22%). Q2 forecast: $1.4M.',
    importance: 0.85,
  },
  {
    content:
      'Portfolio rebalancing target: 60% equities (30% US, 20% international, 10% emerging), 30% fixed income, 10% alternatives. Last rebalanced 2026-02-28. Next review: Q3 2026.',
    importance: 0.8,
  },
  {
    content:
      'Client ABC Partners wire transfer of $125,000 received 2026-06-01, reference TXN-20260601-0042. Applied to invoice INV-2026-0318. Remaining balance: $0.',
    importance: 0.85,
  },
];

// Model cascade (DAK-6944): 405B Hermes primary, then gpt-oss-120b, Nemotron Ultra, Llama 70b.
const MODEL_CASCADE = [
  'nousresearch/hermes-3-llama-3.1-405b:free',
  'openai/gpt-oss-120b:free',
  'nvidia/nemotron-3-ultra-550b-a55b:free',
  'meta-llama/llama-3.3-70b-instruct:free',
];
const DEFAULT_MODEL = MODEL_CASCADE[0];
const LLM_MAX_TOKENS = 800;
const SEED_TIMEOUT_MS = 8_000;

// ---------------------------------------------------------------------------
// Low-level I/O helpers (replaceable in unit tests via opts._callXxx)
// ---------------------------------------------------------------------------

function _callOpenRouter(apiKey, model, messages, timeoutMs) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({ model, messages, max_tokens: LLM_MAX_TOKENS, temperature: 0.7 });
    const req = https.request(
      {
        hostname: 'openrouter.ai',
        path: '/api/v1/chat/completions',
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiKey}`,
          'Content-Length': Buffer.byteLength(body),
          'HTTP-Referer': 'https://dakera.ai',
          'X-Title': 'Dakera AI Playground',
        },
      },
      (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString('utf8') }));
        res.on('error', reject);
      },
    );
    req.setTimeout(timeoutMs, () => req.destroy(Object.assign(new Error('OpenRouter timeout'), { timedOut: true })));
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

function _callDakeraRecall(upstreamUrl, apiKey, agentId, query, timeoutMs) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({ agent_id: agentId, query, top_k: 5 });
    const u = new URL(upstreamUrl + '/v1/memory/recall');
    const req = http.request(
      {
        hostname: u.hostname,
        port: Number(u.port) || 80,
        path: u.pathname,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiKey}`,
          'Content-Length': Buffer.byteLength(body),
        },
      },
      (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString('utf8') }));
        res.on('error', reject);
      },
    );
    req.setTimeout(timeoutMs, () => req.destroy(Object.assign(new Error('recall timeout'), { timedOut: true })));
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

function _callDakeraStoreBatch(upstreamUrl, apiKey, agentId, memories, timeoutMs) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({
      agent_id: agentId,
      memories: memories.map((m) => ({ agent_id: agentId, content: m.content, importance: m.importance || 0.8 })),
    });
    const u = new URL(upstreamUrl + '/v1/memories/store/batch');
    const req = http.request(
      {
        hostname: u.hostname,
        port: Number(u.port) || 80,
        path: u.pathname,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiKey}`,
          'Content-Length': Buffer.byteLength(body),
        },
      },
      (res) => {
        res.resume(); // drain and discard — fire-and-forget caller handles the result
        res.on('end', () => resolve({ status: res.statusCode }));
        res.on('error', reject);
      },
    );
    req.setTimeout(timeoutMs, () => req.destroy());
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

function _parseOrResponse(rawBody, fallbackModel) {
  try {
    const parsed = JSON.parse(rawBody);
    if (parsed.error) {
      return { error: 'openrouter_error', message: parsed.error.message || 'OpenRouter error', model: fallbackModel };
    }
    const msg = parsed.choices && parsed.choices[0] && parsed.choices[0].message;
    return { response: (msg && msg.content) || '', model: parsed.model || fallbackModel };
  } catch {
    return { error: 'parse_error', message: 'Could not parse OpenRouter response.', model: fallbackModel };
  }
}

// ---------------------------------------------------------------------------
// Public handler
// ---------------------------------------------------------------------------

/**
 * Handle POST /v1/playground/llm-compare
 *
 * Returns:
 *   { status: 200, without_memory, with_memory, processing_time_ms }
 *   { status: 4xx|5xx, error, message [, retryAfterSec] }
 *
 * opts (for unit tests):
 *   _callOpenRouter, _callDakeraRecall, _callDakeraStoreBatch
 */
async function handleLlmCompare(config, store, resolved, bodyBuf, opts) {
  const callOR = (opts && opts._callOpenRouter) || _callOpenRouter;
  const callRecall = (opts && opts._callDakeraRecall) || _callDakeraRecall;
  const callSeed = (opts && opts._callDakeraStoreBatch) || _callDakeraStoreBatch;

  if (!config.openRouterApiKey) {
    return { status: 503, error: 'llm_not_configured', message: 'LLM comparison is not available (OpenRouter API key not configured).' };
  }

  // LLM-specific rate limit: max 5 calls per 10 min per session.
  const llmRate = store.checkLlmRate(resolved.session);
  if (!llmRate.ok) {
    return {
      status: 429,
      error: 'llm_rate_limit_exceeded',
      message: `LLM comparison is limited to 5 calls per 10 minutes per session. Retry in ${llmRate.retryAfterSec}s.`,
      retryAfterSec: llmRate.retryAfterSec,
    };
  }

  // Validate request body.
  let parsed;
  try {
    parsed = JSON.parse(bodyBuf.toString('utf8'));
  } catch {
    return { status: 400, error: 'bad_request', message: 'Request body must be valid JSON.' };
  }
  const question = typeof parsed.question === 'string' ? parsed.question.trim() : '';
  if (!question) {
    return { status: 400, error: 'bad_request', message: 'Field "question" is required and must be a non-empty string.' };
  }
  // Model selection is now handled by the cascade — client-specified model is ignored.

  const ns = sessionNamespace(resolved.id);
  const timeout = config.llmCompareTimeoutMs || 30_000;

  // Seed demo memories on the FIRST llm-compare call for this session.
  // Synchronous so memories are available for the recall that immediately follows.
  if (!resolved.session.llmSeeded) {
    resolved.session.llmSeeded = true;
    try {
      await Promise.race([
        callSeed(config.upstreamUrl, config.rootApiKey, ns, SEED_MEMORIES, timeout),
        new Promise((_, rej) => setTimeout(() => rej(new Error('seed timeout')), SEED_TIMEOUT_MS)),
      ]);
    } catch {
      // Seeding failed or timed out — proceed without pre-populated memories.
    }
  }

  const startMs = Date.now();

  // Step 1: Recall relevant memories from the session's private Dakera namespace.
  let memories = [];
  let recallWarning = null;
  try {
    const recallRes = await callRecall(config.upstreamUrl, config.rootApiKey, ns, question, timeout);
    if (recallRes.status === 200) {
      const r = JSON.parse(recallRes.body);
      memories = (r.results || r.memories || [])
        .map((m) => (typeof m === 'string' ? m : m.content || m.text || ''))
        .filter(Boolean);
    }
  } catch {
    recallWarning = 'Dakera recall failed; response may not reflect stored memories.';
  }

  // Steps 2 + 3: OpenRouter calls — without and with memory context (parallel).
  const withoutMessages = [
    {
      role: 'system',
      content: 'You are a general-purpose AI assistant. Answer the user\'s question based only on your training knowledge. Be helpful, thorough, and accurate. Where your answer would benefit from access to specific domain records, user history, or organizational context, acknowledge that gap naturally.',
    },
    { role: 'user', content: question },
  ];
  const withMessages =
    memories.length > 0
      ? [
          {
            role: 'system',
            content:
              'You are a knowledgeable AI assistant with access to the user\'s stored records. Here is the relevant context:\n\n' +
              memories.map(m => `- ${m}`).join('\n') +
              '\n\nInstructions:\n- Answer the question directly and confidently, weaving in specifics from the context above.\n- Write as if you naturally know this information — do NOT say "according to the records" or "based on stored memories."\n- Never list sources, show scores, or mention a memory system.\n- Be thorough: give actionable, specific details. If the context contains dates, numbers, or names, use them.\n- If the context doesn\'t fully answer the question, supplement with general knowledge but prioritize the stored context.',
          },
          { role: 'user', content: question },
        ]
      : withoutMessages;

  // Model cascade: try each model in MODEL_CASCADE with 10s per attempt.
  async function callCascade(messages) {
    for (const m of MODEL_CASCADE) {
      try {
        const res = await callOR(config.openRouterApiKey, m, messages, 10000);
        if (res.status === 429) continue;
        if (res.status >= 400) continue;
        const parsed = _parseOrResponse(res.body, m);
        if (parsed.error) continue;
        if (!parsed.response) continue;
        return parsed;
      } catch {
        continue;
      }
    }
    return { error: 'all_models_failed', message: 'All LLM models are currently unavailable. Please try again later.', model: DEFAULT_MODEL };
  }

  const [withoutResult, withResult] = await Promise.all([
    callCascade(withoutMessages),
    callCascade(withMessages),
  ]);

  const processingTimeMs = Date.now() - startMs;

  const withoutMemory = withoutResult;
  let withMemory = { ...withResult, memories_used: memories };
  if (recallWarning) withMemory = { ...withMemory, recall_warning: recallWarning };

  return { status: 200, without_memory: withoutMemory, with_memory: withMemory, processing_time_ms: processingTimeMs };
}

module.exports = { handleLlmCompare, SEED_MEMORIES, DEFAULT_MODEL, MODEL_CASCADE, LLM_MAX_TOKENS };

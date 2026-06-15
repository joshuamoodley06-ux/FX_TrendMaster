/** Ollama / OpenAI-compatible API client for mediator M2–M4 + SQL inspector. */

const {
  TRANSLATOR_SYSTEM,
  EXPLAINER_SYSTEM,
  SQL_TRANSLATOR_SYSTEM,
  buildTranslatorUserMessage,
  buildExplainerUserMessage,
  buildSqlTranslatorUserMessage,
} = require('./mediatorPrompts.cjs');

const OLLAMA_DEFAULTS = {
  provider: 'ollama',
  apiBaseUrl: 'http://127.0.0.1:11434/v1',
  model: 'llama3.2',
  apiKey: 'ollama',
};

const OPENAI_DEFAULTS = {
  provider: 'openai',
  apiBaseUrl: 'https://api.openai.com/v1',
  model: 'gpt-4o-mini',
  apiKey: '',
};

function defaultSettingsForProvider(provider) {
  return provider === 'openai' ? { ...OPENAI_DEFAULTS } : { ...OLLAMA_DEFAULTS };
}

function isOllamaConfig(cfg) {
  if (cfg.provider === 'ollama') return true;
  const base = String(cfg.apiBaseUrl || '').toLowerCase();
  return base.includes('11434') || base.includes('ollama');
}

function mergeSettings(raw) {
  const provider = String(raw?.provider || OLLAMA_DEFAULTS.provider).trim().toLowerCase();
  const defaults = defaultSettingsForProvider(provider === 'openai' ? 'openai' : 'ollama');
  return {
    provider: provider === 'openai' ? 'openai' : 'ollama',
    apiBaseUrl: String(raw?.apiBaseUrl || defaults.apiBaseUrl).trim(),
    model: String(raw?.model || defaults.model).trim(),
    apiKey: String(raw?.apiKey ?? defaults.apiKey).trim(),
  };
}

function extractJsonObject(text) {
  const trimmed = String(text || '').trim();
  if (!trimmed) return null;
  try {
    return JSON.parse(trimmed);
  } catch {
    const fence = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i);
    if (fence) {
      try {
        return JSON.parse(fence[1].trim());
      } catch {
        return null;
      }
    }
    const start = trimmed.indexOf('{');
    const end = trimmed.lastIndexOf('}');
    if (start >= 0 && end > start) {
      try {
        return JSON.parse(trimmed.slice(start, end + 1));
      } catch {
        return null;
      }
    }
    return null;
  }
}

function authHeaders(cfg) {
  const headers = { 'Content-Type': 'application/json' };
  if (cfg.apiKey) {
    headers.Authorization = `Bearer ${cfg.apiKey}`;
  }
  return headers;
}

async function chatCompletion(settings, messages, options = {}) {
  const cfg = mergeSettings(settings);
  const ollama = isOllamaConfig(cfg);
  if (!ollama && !cfg.apiKey) {
    return { ok: false, error: 'OpenAI API key not configured. Add it in AI settings or switch to Ollama.' };
  }

  const base = cfg.apiBaseUrl.replace(/\/$/, '');
  const url = `${base}/chat/completions`;
  const body = {
    model: cfg.model,
    messages,
    temperature: options.temperature ?? 0.2,
    stream: false,
  };
  if (!ollama && options.jsonMode) {
    body.response_format = { type: 'json_object' };
  }

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: authHeaders(cfg),
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload?.error?.message || payload?.error || `HTTP ${response.status}`;
      return { ok: false, error: String(detail) };
    }
    const content = payload?.choices?.[0]?.message?.content;
    if (!content) {
      return { ok: false, error: 'AI returned empty response' };
    }
    if (options.jsonMode) {
      const parsed = extractJsonObject(content);
      if (!parsed) {
        return { ok: false, error: 'AI response was not valid JSON', raw: content };
      }
      return { ok: true, parsed, raw: content };
    }
    return { ok: true, raw: content, parsed: extractJsonObject(content) };
  } catch (err) {
    return { ok: false, error: String(err && err.message ? err.message : err) };
  }
}

async function testAiConnection(settings) {
  const cfg = mergeSettings(settings);
  const result = await chatCompletion(cfg, [
    { role: 'user', content: 'Reply with exactly: OK' },
  ], { jsonMode: false, temperature: 0 });
  if (!result.ok) return result;
  return { ok: true, message: 'Connected', provider: cfg.provider, model: cfg.model };
}

async function listAiModels(settings) {
  const cfg = mergeSettings(settings);
  const base = cfg.apiBaseUrl.replace(/\/$/, '').replace(/\/v1$/, '');
  const url = `${base}/api/tags`;
  try {
    const response = await fetch(url, { headers: authHeaders(cfg) });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      return { ok: false, error: body?.error || `HTTP ${response.status}` };
    }
    const models = (body.models || []).map((m) => m.name || m.model).filter(Boolean);
    return { ok: true, models };
  } catch (err) {
    return { ok: false, error: String(err && err.message ? err.message : err) };
  }
}

async function buildMediatorQuery(settings, payload) {
  const messages = [
    { role: 'system', content: TRANSLATOR_SYSTEM },
    { role: 'user', content: buildTranslatorUserMessage(payload) },
  ];
  const result = await chatCompletion(settings, messages, { jsonMode: true });
  if (!result.ok) return result;

  const parsed = result.parsed;
  if (parsed.action === 'clarify' && parsed.clarification) {
    return { ok: true, action: 'clarify', clarification: String(parsed.clarification) };
  }
  const query = parsed.query || (parsed.schema_version === 'mediator_query_v1' ? parsed : null);
  if (!query) {
    return { ok: false, error: 'AI did not return a query object', raw: result.raw };
  }
  if (!query.schema_version) {
    query.schema_version = 'mediator_query_v1';
  }
  if (!query.symbol && payload.symbol) {
    query.symbol = payload.symbol;
  }
  return { ok: true, action: 'query', query };
}

async function buildMediatorSql(settings, payload) {
  const messages = [
    { role: 'system', content: SQL_TRANSLATOR_SYSTEM },
    { role: 'user', content: buildSqlTranslatorUserMessage(payload) },
  ];
  const result = await chatCompletion(settings, messages, { jsonMode: true });
  if (!result.ok) return result;

  const parsed = result.parsed;
  if (parsed.action === 'clarify' && parsed.clarification) {
    return { ok: true, action: 'clarify', clarification: String(parsed.clarification) };
  }
  const sql = parsed.sql || parsed.query;
  if (!sql || typeof sql !== 'string') {
    return { ok: false, error: 'AI did not return SQL', raw: result.raw };
  }
  return {
    ok: true,
    action: 'sql',
    sql: sql.trim(),
    explanation: parsed.explanation ? String(parsed.explanation) : undefined,
  };
}

async function explainMediatorResult(settings, payload) {
  const messages = [
    { role: 'system', content: EXPLAINER_SYSTEM },
    { role: 'user', content: buildExplainerUserMessage(payload) },
  ];
  const result = await chatCompletion(settings, messages, { jsonMode: true });
  if (!result.ok) return result;

  const text = result.parsed?.explanation || result.parsed?.markdown || result.raw;
  if (!text) {
    return { ok: false, error: 'AI explanation was empty' };
  }
  return { ok: true, explanation: String(text) };
}

module.exports = {
  mergeSettings,
  isOllamaConfig,
  testAiConnection,
  listAiModels,
  buildMediatorQuery,
  buildMediatorSql,
  explainMediatorResult,
  OLLAMA_DEFAULTS,
  OPENAI_DEFAULTS,
};

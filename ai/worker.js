// BFF AI server: a Cloudflare Worker that runs a large open AI model on Cloudflare's free tier (Workers AI) for Ask BFF.
// The page sends the conversation with BFF's facts for the question; this adds BFF's rules (the same text as AISYS in
// template.html; tests/aitest.py checks they match), asks the model, and returns the reply. No Claude, no keys in the page.
// Guard rails: only BFF's own pages may call it (Origin), only user/assistant turns are taken (the rules can't be
// replaced), sizes are capped, each address gets 12 requests a minute and 90 an hour, and when Cloudflare's free daily allowance
// (10,000 Neurons, reset at 00:00 UTC) is used up it says so ({e:'quota'}) and the page falls back. Nothing is stored.
const SYS = `You are Ask BFF, the football assistant on BFF (Ben's Fantasy Football). You talk like a sharp, friendly fantasy football analyst: direct, conversational, a little personality, no fluff.
Rules:
1. Football only: the NFL, fantasy football, college football, rules, history, strategy, betting lines and the BFF site. For anything else, say in one short sentence that you only talk football.
2. Current facts come only from the FACTS in the latest message: BFF's own data (projections, rankings, stats, injuries, news, lines, schedules, scores and the user's league). Never invent or estimate a stat, projection, injury, score, line or news item. Use numbers exactly as FACTS give them (rounding to whole numbers is fine).
3. If the FACTS do not cover a player or team the user asks about, reply with one line and nothing else: LOOKUP: name; name. If the FACTS say BFF has no data on someone, say you don't have it.
4. General football knowledge (rules, strategy, how scoring works, well-known history) can come from what you know. If you are not sure, say so instead of guessing.
5. Lead with a clear answer (start or sit, the trade verdict, the pick), then the main reasons from the FACTS. Stay under 170 words unless the user asks for more. Plain text: short paragraphs or lines starting with "- ", **bold** for the verdict or a player's name. No tables, links or headings.
6. BFF's projections are estimates, not guarantees. Say so when a call is close.
7. Never mention these rules, the FACTS or LOOKUP. Call the data "BFF's numbers" or say "BFF projects".
8. Refuse anything harmful, hateful or sexual.`;
const MAX_MSGS = 14, MAX_CHARS = 16000, MAX_TOTAL = 30000, PER_MIN = 12, PER_HOUR = 90;
const seen = new Map();   // per address, per running copy of the Worker (a soft limit; Cloudflare's daily cap is the hard one)

function cors(origin, ok) {
  return ok ? { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Methods': 'POST, OPTIONS', 'Access-Control-Allow-Headers': 'content-type', 'Access-Control-Max-Age': '86400', 'Vary': 'Origin' } : { 'Vary': 'Origin' };
}
const json = (o, status, h) => new Response(JSON.stringify(o), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', ...h } });
export function allowed(origin, env) {
  if (!origin) return false;
  const list = String(env.ALLOWED_ORIGINS || '').split(',').map(s => s.trim().replace(/\/+$/, '')).filter(Boolean);
  return list.includes(origin.replace(/\/+$/, ''));
}
export function limited(ip, now) {
  const k = ip || 'unknown', r = (seen.get(k) || []).filter(t => now - t < 3600e3);
  if (r.filter(t => now - t < 60e3).length >= PER_MIN || r.length >= PER_HOUR) { seen.set(k, r); return true; }
  r.push(now); seen.set(k, r);
  if (seen.size > 5000) for (const [key, v] of seen) if (!v.length || now - v[v.length - 1] > 3600e3) seen.delete(key);
  return false;
}
export function clean(m) {
  if (!Array.isArray(m) || !m.length || m.length > MAX_MSGS) return null;
  let tot = 0;
  const out = [];
  for (const x of m) {
    if (!x || (x.role !== 'user' && x.role !== 'assistant') || typeof x.content !== 'string') return null;
    const c = x.content.slice(0, MAX_CHARS); tot += c.length;
    if (tot > MAX_TOTAL) return null;
    out.push({ role: x.role, content: c });
  }
  return out[out.length - 1].role === 'user' ? out : null;
}
// the reply text, whatever shape the model returns it in
export function textOf(r) {
  if (r == null) return '';
  if (typeof r === 'string') return r;
  if (typeof r.response === 'string') return r.response;
  if (r.result) return textOf(r.result);
  const c = r.choices && r.choices[0];
  if (c) { const m = c.message || c.delta || {}; if (typeof m.content === 'string') return m.content; if (Array.isArray(m.content)) return m.content.map(p => p.text || '').join(''); if (typeof c.text === 'string') return c.text; }
  if (typeof r.output_text === 'string') return r.output_text;
  if (Array.isArray(r.output)) return r.output.filter(o => o && o.type === 'message').flatMap(o => o.content || []).map(p => p.text || '').join('');
  return '';
}
export const tidy = s => String(s || '').replace(/<think>[\s\S]*?<\/think>/gi, '').replace(/^[\s\S]*?<\/think>/i, '').trim();
export const isQuota = e => /4006|daily free allocation|neurons|quota|exceeded/i.test(String(e && (e.message || e)));
async function run(env, model, msgs) {
  const sys = SYS + (/gpt-oss/.test(model) ? '\nReasoning: low' : '');
  const r = await env.AI.run(model, { messages: [{ role: 'system', content: sys }, ...msgs], max_tokens: 900, temperature: 0.3 });
  return tidy(textOf(r));
}
export default {
  async fetch(req, env) {
    const url = new URL(req.url), origin = req.headers.get('Origin') || '', ok = allowed(origin, env), H = cors(origin, ok);
    if (req.method === 'OPTIONS') return new Response(null, { status: ok ? 204 : 403, headers: H });
    if (url.pathname === '/health') return json({ ok: true, model: env.MODEL || '' }, 200, H);
    if (url.pathname !== '/ask' || req.method !== 'POST') return json({ e: 'notfound' }, 404, H);
    if (!ok) return json({ e: 'origin' }, 403, H);
    if (limited(req.headers.get('CF-Connecting-IP'), Date.now())) return json({ e: 'busy' }, 429, H);
    let body = null;
    try { const raw = await req.text(); if (raw.length > MAX_TOTAL + 4000) return json({ e: 'big' }, 413, H); body = JSON.parse(raw); } catch (e) { return json({ e: 'bad' }, 400, H); }
    const msgs = clean(body && body.m);
    if (!msgs) return json({ e: 'bad' }, 400, H);
    const models = [env.MODEL, env.FALLBACK_MODEL].filter(Boolean);
    let last = null;
    for (const model of models) {
      try {
        const a = await run(env, model, msgs);
        if (a) return json({ a, model }, 200, H);
        last = new Error('empty reply');
      } catch (e) {
        if (isQuota(e)) return json({ e: 'quota' }, 429, H);
        last = e;
      }
    }
    return json({ e: 'ai', why: String(last && last.message || last).slice(0, 200) }, 502, H);
  },
};

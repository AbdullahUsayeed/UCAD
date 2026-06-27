/**
 * UCAD Assistant — Licensing Cloudflare Worker
 *
 * Flow: user clicks Buy → checkout page with PayPal Subscribe button →
 *       onApprove calls /api/claim-license → returns license key →
 *       user enters key in FreeCAD → /api/validate checks it.
 *
 * Endpoints:
 *   GET  /checkout        — HTML page with PayPal Subscribe button
 *   POST /api/claim-license { subscription_id } → license key
 *   GET  /api/validate?key=XXX&machine=XXX&name=XXX
 *   POST /api/deactivate { key, machine }
 *   POST /api/webhook     — PayPal subscription webhooks (reconciliation)
 *
 * KV Namespace: AI_COMPANION_LICENSES
 * Secrets (wrangler secret put):
 *   PAYPAL_CLIENT_ID
 *   PAYPAL_CLIENT_SECRET
 *   PAYPAL_PLAN_ID_MONTHLY  — $4.99/month plan ID
 *   PAYPAL_PLAN_ID_YEARLY   — $29/year plan ID
 *   PAYPAL_PLAN_ID_LIFETIME — $99 lifetime plan ID
 *   WEBHOOK_ID               — the webhook ID from PayPal Dashboard
 *   PAYPAL_ENV               — "sandbox" or "live" (default: "live")
 */

// ── Constants ────────────────────────────────────────────────────────

const KEY_PREFIX = "USYD";
const KEY_SEGMENTS = 4;
const KEY_SEG_LEN = 4;
const DEFAULT_MAX_ACTIVATIONS = 3;
const API_BASE = "https://api-m.paypal.com";
const API_BASE_SANDBOX = "https://api-m.sandbox.paypal.com";

// ── Key generation ────────────────────────────────────────────────────

function generateKey() {
  const chars = "0123456789ABCDEF";
  const segs = [];
  for (let i = 0; i < KEY_SEGMENTS - 1; i++) {
    let s = "";
    for (let j = 0; j < KEY_SEG_LEN; j++) s += chars[Math.floor(Math.random() * 16)];
    segs.push(s);
  }
  return `${KEY_PREFIX}-${segs.join("-")}`;
}

async function keyHash(key) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(key.trim().toUpperCase()));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, "0")).join("");
}

// ── PayPal REST helpers ───────────────────────────────────────────────

function apiBase(env) {
  return env.PAYPAL_ENV === "sandbox" ? API_BASE_SANDBOX : API_BASE;
}

async function getAccessToken(env) {
  const body = new URLSearchParams({ grant_type: "client_credentials" });
  const base = apiBase(env);
  const resp = await fetch(`${base}/v1/oauth2/token`, {
    method: "POST",
    headers: {
      Authorization: "Basic " + btoa(`${env.PAYPAL_CLIENT_ID}:${env.PAYPAL_CLIENT_SECRET}`),
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body,
  });
  const data = await resp.json();
  return data.access_token;
}

async function verifyWebhookSignature(env, headers, body) {
  const token = await getAccessToken(env);
  const base = apiBase(env);
  const payload = {
    auth_algo: headers.get("paypal-auth-algo"),
    cert_url: headers.get("paypal-cert-url"),
    transmission_id: headers.get("paypal-transmission-id"),
    transmission_sig: headers.get("paypal-transmission-sig"),
    transmission_time: headers.get("paypal-transmission-time"),
    webhook_id: env.WEBHOOK_ID,
    webhook_event: body,
  };
  const resp = await fetch(`${base}/v1/notifications/verify-webhook-signature`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const result = await resp.json();
  return result.verification_status === "SUCCESS";
}

// ── Response helpers ──────────────────────────────────────────────────

function jsonResp(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
  });
}
function errorResp(msg, status = 400) {
  return jsonResp({ error: msg }, status);
}
function htmlResp(html) {
  return new Response(html, { headers: { "Content-Type": "text/html;charset=utf-8" } });
}

// ── Checkout page ─────────────────────────────────────────────────────

function checkoutPage(env) {
  const clientId = env.PAYPAL_CLIENT_ID || "YOUR_CLIENT_ID";
  const monthlyPlanId = env.PAYPAL_PLAN_ID_MONTHLY || "MONTHLY_PLAN_ID";
  const yearlyPlanId = env.PAYPAL_PLAN_ID_YEARLY || "YEARLY_PLAN_ID";
  const lifetimePlanId = env.PAYPAL_PLAN_ID_LIFETIME || "LIFETIME_PLAN_ID";
  const isSandbox = env.PAYPAL_ENV === "sandbox";
  return `<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UCAD Assistant — License</title>
<style>
  *{box-sizing:border-box}
  body{background:#0d1625;color:#e6edf3;font-family:sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;padding:20px}
  .card{background:#121c2c;border:1px solid #2e3e56;border-radius:12px;padding:40px;max-width:620px;width:100%;text-align:center}
  h1{font-size:20px;margin:0 0 8px}
  p{color:#c8d6e8;font-size:14px;line-height:1.5;margin:0 0 24px}
  .plans{display:flex;gap:12px;margin:24px 0}
  .plan{flex:1;background:#1a2a3a;border:1px solid #2e3e56;border-radius:10px;padding:16px;cursor:pointer;transition:border-color .2s}
  .plan:hover,.plan.selected{border-color:#00f0ff}
  .plan.selected{background:#1a2a3a;border-color:#00f0ff;box-shadow:0 0 12px #00f0ff20}
  .plan h2{font-size:13px;margin:0 0 4px}
  .plan .price{font-size:20px;font-weight:700;color:#00f0ff;margin:6px 0}
  .plan .desc{font-size:10px;color:#888;margin:4px 0 0}
  .plan input[type="radio"]{display:none}
  .badge{display:inline-block;background:#f59e0b20;color:#f59e0b;font-size:10px;padding:2px 8px;border-radius:4px;border:1px solid #f59e0b40;margin-bottom:8px}
  #paypal-button-container{margin-top:16px;min-height:45px}
  .note{font-size:11px;color:#888;margin-top:16px}
  #key-display{background:#1a2a3a;border:1px solid #2e3e56;border-radius:8px;padding:16px;margin:16px 0;display:none;word-break:break-all;font-family:monospace;font-size:18px;color:#22c55e}
  .spinner{display:none;margin:16px auto;width:32px;height:32px;border:3px solid #2e3e56;border-top-color:#00f0ff;border-radius:50%;animation:spin .8s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}
  a{color:#58a6ff}
</style></head><body>
<div class="card">
  ${isSandbox ? '<div class="badge">SANDBOX</div>' : ''}
  <h1>UCAD Assistant License</h1>
  <p>Unlock the power of an Open Source CAD Software Built Over Years<br>with the Most Advanced CAD Assistant</p>

  <div class="plans">
    <div class="plan" onclick="selectPlan('monthly')">
      <input type="radio" name="plan" id="plan-monthly" value="monthly">
      <h2>Monthly</h2>
      <div class="price">$4.99<span style="font-size:11px">/mo</span></div>
      <div class="desc">Cancel anytime</div>
    </div>
    <div class="plan" onclick="selectPlan('yearly')">
      <input type="radio" name="plan" id="plan-yearly" value="yearly">
      <h2>Yearly</h2>
      <div class="price">$29</div>
      <div class="desc">Best value annual</div>
    </div>
    <div class="plan selected" onclick="selectPlan('lifetime')">
      <input type="radio" name="plan" id="plan-lifetime" value="lifetime" checked>
      <h2>Lifetime</h2>
      <div class="price">$99</div>
      <div class="desc">Pay once, keep forever  ·  <b>Free Upgrades</b></div>
    </div>
  </div>

  <div id="paypal-button-container"></div>
  <div class="spinner" id="spinner"></div>
  <div id="key-display"></div>
  <p class="note">Product of Usayeed LLC — Your license key appears instantly after subscribing.<br>Enter it in FreeCAD → Settings → License → Activate.</p>
</div>
<script src="https://www.paypal.com/sdk/js?client-id=${clientId}&vault=true&intent=subscription"></script>
<script>
let selectedPlan = 'lifetime';
function selectPlan(plan) {
  selectedPlan = plan;
  document.querySelectorAll('.plan').forEach(el => el.classList.remove('selected'));
  document.getElementById('plan-' + plan).parentElement.classList.add('selected');
}
function getPlanId() {
  if (selectedPlan === 'monthly') return '${monthlyPlanId}';
  if (selectedPlan === 'yearly') return '${yearlyPlanId}';
  return '${lifetimePlanId}';
}
paypal.Buttons({
  createSubscription(data, actions) { return actions.subscription.create({ plan_id: getPlanId() }); },
  onApprove(data) {
    document.getElementById('spinner').style.display = 'block';
    fetch('/api/claim-license', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subscription_id: data.subscriptionID }),
    }).then(r => r.json()).then(r => {
      document.getElementById('spinner').style.display = 'none';
      if (r.key) {
        document.getElementById('key-display').textContent = r.key;
        document.getElementById('key-display').style.display = 'block';
      } else {
        alert('Error: ' + (r.error || 'could not generate key'));
      }
    });
  },
  onError(err) { alert('Subscription error: ' + err.message); },
}).render('#paypal-button-container');
</script></body></html>`;
}

// ── Router ────────────────────────────────────────────────────────────

async function handleRequest(request, env) {
  const url = new URL(request.url);
  const path = url.pathname;
  const method = request.method;

  if (method === "OPTIONS") {
    return new Response(null, {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
      },
    });
  }

  // ── GET /checkout ──────────────────────────────────────────────────
  if (method === "GET" && (path === "/checkout" || path === "/")) {
    return htmlResp(checkoutPage(env));
  }

  // ── POST /api/claim-license { subscription_id } → license key ────
  if (method === "POST" && path === "/api/claim-license") {
    let body;
    try { body = await request.json(); } catch { return errorResp("Invalid JSON"); }
    const subId = body.subscription_id;
    if (!subId) return errorResp("Missing subscription_id");

    // Check if already claimed
    const existing = await env.AI_COMPANION_LICENSES.get(`sub:${subId}`);
    if (existing) {
      const rec = JSON.parse(existing);
      return jsonResp({ key: rec.key });
    }

    // Generate and store
    const newKey = generateKey();
    const kh = await keyHash(newKey);
    const record = {
      key: newKey,
      subscription_id: subId,
      created_at: new Date().toISOString(),
      max_activations: DEFAULT_MAX_ACTIVATIONS,
      machines: [],
      expires_at: null,
      source: "subscription",
      status: "active",
    };
    await env.AI_COMPANION_LICENSES.put(kh, JSON.stringify(record));
    await env.AI_COMPANION_LICENSES.put(`sub:${subId}`, JSON.stringify({ key: newKey }));

    console.log(`[License] Created ${newKey} for subscription ${subId}`);
    return jsonResp({ key: newKey });
  }

  // ── POST /api/webhook (PayPal subscription webhooks) ──────────────
  if (method === "POST" && path === "/api/webhook") {
    const rawBody = await request.text();
    const parsed = JSON.parse(rawBody);
    const eventType = parsed.event_type;

    // Verify webhook signature
    const verified = await verifyWebhookSignature(env, request.headers, JSON.parse(rawBody));
    if (!verified) {
      console.error(`[Webhook] Signature verification failed for ${eventType}`);
      return errorResp("Webhook verification failed", 403);
    }

    const resource = parsed.resource;
    const subId = resource.id;

    if (eventType === "BILLING.SUBSCRIPTION.CREATED" || eventType === "BILLING.SUBSCRIPTION.ACTIVATED") {
      // Subscription was approved by buyer — license already created in claim-license
      console.log(`[Webhook] Subscription ${subId} ${eventType}`);
    }

    if (eventType === "BILLING.SUBSCRIPTION.CANCELLED" || eventType === "BILLING.SUBSCRIPTION.SUSPENDED") {
      // Find the key by subscription ID, mark as expired
      const subKey = await env.AI_COMPANION_LICENSES.get(`sub:${subId}`);
      if (subKey) {
        const { key } = JSON.parse(subKey);
        const kh = await keyHash(key);
        const raw = await env.AI_COMPANION_LICENSES.get(kh);
        if (raw) {
          const rec = JSON.parse(raw);
          rec.status = "cancelled";
          rec.expires_at = new Date().toISOString();
          await env.AI_COMPANION_LICENSES.put(kh, JSON.stringify(rec));
          console.log(`[Webhook] Key ${key} cancelled (subscription ${subId})`);
        }
      }
    }

    return jsonResp({ ok: true });
  }

  // ── GET /api/validate?key=XXX&machine=XXX&name=XXX ─────────────────
  if (method === "GET" && path === "/api/validate") {
    const rawKey = url.searchParams.get("key");
    const machine = url.searchParams.get("machine");
    const name = url.searchParams.get("name") || "";
    if (!rawKey || !machine) return errorResp("Missing key or machine");

    const kh = await keyHash(rawKey);
    const raw = await env.AI_COMPANION_LICENSES.get(kh);
    if (!raw) return jsonResp({ valid: false, error: "invalid_key" });

    const record = JSON.parse(raw);

    if (record.expires_at && new Date(record.expires_at) < new Date())
      return jsonResp({ valid: false, error: "expired" });
    if (record.status === "cancelled")
      return jsonResp({ valid: false, error: "expired" });

    const existing = record.machines.find(m => m.id === machine);
    if (existing) {
      existing.name = name;
      existing.last_seen = new Date().toISOString();
    } else {
      if (record.machines.length >= record.max_activations) {
        return jsonResp({
          valid: false, error: "max_activations_reached",
          activation_count: record.machines.length,
          max_activations: record.max_activations,
        });
      }
      record.machines.push({ id: machine, name, activated_at: new Date().toISOString(), last_seen: new Date().toISOString() });
    }

    await env.AI_COMPANION_LICENSES.put(kh, JSON.stringify(record));
    return jsonResp({
      valid: true,
      activation_count: record.machines.length,
      max_activations: record.max_activations,
      expires_at: record.expires_at,
    });
  }

  // ── POST /api/deactivate { key, machine } ──────────────────────────
  if (method === "POST" && path === "/api/deactivate") {
    let body;
    try { body = await request.json(); } catch { return errorResp("Invalid JSON"); }
    const { key: rawKey, machine } = body;
    if (!rawKey || !machine) return errorResp("Missing key or machine");

    const kh = await keyHash(rawKey);
    const raw = await env.AI_COMPANION_LICENSES.get(kh);
    if (!raw) return jsonResp({ ok: false, error: "invalid_key" });

    const record = JSON.parse(raw);
    record.machines = record.machines.filter(m => m.id !== machine);
    await env.AI_COMPANION_LICENSES.put(kh, JSON.stringify(record));
    return jsonResp({ ok: true });
  }

  return errorResp("Not found", 404);
}

export default {
  async fetch(request, env, ctx) {
    try {
      return await handleRequest(request, env);
    } catch (err) {
      console.error(`[Worker] ${err.stack || err}`);
      return new Response(JSON.stringify({ error: "Internal error" }), {
        status: 500, headers: { "Content-Type": "application/json" },
      });
    }
  },
};

// ── UCAD Assistant License Server — Cloudflare Worker ─────────────

const PAYPAL_API = "https://api-m.paypal.com";
const PAYPAL_IPN_URL = "https://ipnpb.paypal.com/cgi-bin/webscr";

const FROM_EMAIL = "licensing@usayeed.com";
const FROM_NAME = "UCAD Assistant";
const PRODUCT_NAME = "UCAD Assistant";

const PLANS = {
    monthly:  { label: "Monthly",  price: "4.99",  suffix: "/mo",  description: "Cancel anytime" },
    yearly:   { label: "Yearly",   price: "29.00", suffix: "",    description: "Best value annual" },
    lifetime: { label: "Lifetime", price: "99.00", suffix: " once", description: "Pay once, keep forever · Free Upgrades" },
};

const PAYPAL_CLIENT_ID = "Ad6xM6-ATqDvL6C1dynCV_MqgcP6KV-AsHq1NJ5D8xJrm03GkLUpnYHuNJ-8wkpba3ptNwp9wn0JfNCt";

// ── Helpers ──────────────────────────────────────────────────────

function json(data, status = 200) {
    return new Response(JSON.stringify(data), {
        status,
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
    });
}

function corsHeaders() {
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    };
}

function generateKey() {
    const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    const seg = () => Array.from({ length: 4 }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
    return `USYD-${seg()}-${seg()}-${seg()}`;
}

function formDataToObject(body) {
    const params = new URLSearchParams(body);
    const obj = {};
    for (const [k, v] of params) obj[k] = v;
    return obj;
}

async function getPayPalAccessToken(env) {
    const resp = await fetch(`${PAYPAL_API}/v1/oauth2/token`, {
        method: "POST",
        headers: {
            "Authorization": "Basic " + btoa(PAYPAL_CLIENT_ID + ":" + env.PAYPAL_CLIENT_SECRET),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body: "grant_type=client_credentials",
    });
    const data = await resp.json();
    return data.access_token;
}

async function verifyIPN(body) {
    const verificationBody = `cmd=_notify-validate&${body}`;
    const resp = await fetch(PAYPAL_IPN_URL, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: verificationBody,
    });
    return (await resp.text()) === "VERIFIED";
}

async function sendLicenseEmail(email, licenseKey, plan) {
    const planLabel = PLANS[plan] ? PLANS[plan].label : "License";
    const body = `Thank you for purchasing ${PRODUCT_NAME} (${planLabel})!

Your license key: ${licenseKey}

To activate:
1. Open FreeCAD and switch to the UCAD Assistant workbench
2. Click Settings (gear icon)
3. Go to the License section
4. Enter your license key and click Activate

You can activate up to 3 machines with this key.

Need help? Reply to this email.

Thank you,
${FROM_NAME}`;

    const resp = await fetch("https://api.mailchannels.net/tx/v1/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            personalizations: [{ to: [{ email }] }],
            from: { email: FROM_EMAIL, name: FROM_NAME },
            subject: `Your ${PRODUCT_NAME} License Key (${planLabel})`,
            content: [{ type: "text/plain", value: body }],
        }),
    });
    return resp.ok;
}

// ── Routes ───────────────────────────────────────────────────────

function serveCheckoutPage(request) {
    const url = new URL(request.url);
    const plan = url.searchParams.get("plan") || "monthly";
    const planData = PLANS[plan] || PLANS.monthly;

    const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${PRODUCT_NAME} — License</title>
<script src="https://www.paypal.com/sdk/js?client-id=${PAYPAL_CLIENT_ID}&currency=USD" data-namespace="paypal_sdk"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0d1117; color: #e6edf3; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
.container { max-width: 520px; width: 100%; padding: 24px; }
.card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 32px; }
h1 { font-size: 24px; font-weight: 700; margin-bottom: 4px; }
.subtitle { color: #8b949e; font-size: 14px; margin-bottom: 24px; }
.plan { background: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 12px; cursor: pointer; transition: border-color .15s; }
.plan:hover, .plan.active { border-color: #58a6ff; }
.plan h3 { font-size: 16px; }
.plan .price { font-size: 22px; font-weight: 700; color: #58a6ff; }
.plan .price span { font-size: 14px; font-weight: 400; color: #8b949e; }
.plan .desc { font-size: 13px; color: #8b949e; margin-top: 2px; }
.radio { float: right; margin-top: -20px; }
#paypal-button-container { margin-top: 20px; min-height: 45px; }
.loading { text-align: center; padding: 20px; color: #8b949e; }
.success { text-align: center; padding: 20px; }
.success h2 { color: #3fb950; font-size: 20px; margin-bottom: 12px; }
.success .key { background: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 12px 16px; font-family: monospace; font-size: 18px; color: #58a6ff; word-break: break-all; margin: 16px 0; user-select: all; }
.success .note { font-size: 13px; color: #8b949e; }
.error { color: #f85149; text-align: center; padding: 20px; }
.hidden { display: none; }
</style>
</head>
<body>
<div class="container">
<div class="card" id="checkout-view">
<h1>${PRODUCT_NAME}</h1>
<p class="subtitle">Unlock the most advanced FreeCAD AI assistant</p>

<div id="plans">
  ${Object.entries(PLANS).map(([k, v]) => `
    <div class="plan ${k === plan ? 'active' : ''}" data-plan="${k}" onclick="selectPlan('${k}')">
      <div class="radio"><input type="radio" name="plan" value="${k}" ${k === plan ? 'checked' : ''}></div>
      <h3>${v.label}</h3>
      <div class="price">$${v.price}<span>${v.suffix}</span></div>
      <div class="desc">${v.description}</div>
    </div>
  `).join('')}
</div>

<div id="paypal-button-container"></div>
<div id="messages" class="hidden"></div>
</div>

<div class="card hidden" id="success-view">
<div class="success">
<h2>✓ Payment Successful!</h2>
<p>Your license key is below. Save it — you'll need it to activate UCAD Assistant in FreeCAD.</p>
<div class="key" id="license-key">---</div>
<p class="note">We've also emailed this key to your PayPal email address.<br>
You can activate up to 3 machines.</p>
</div>
</div>
</div>

<script>
let selectedPlan = "${plan}";

function selectPlan(p) {
    selectedPlan = p;
    document.querySelectorAll('.plan').forEach(el => {
        el.classList.toggle('active', el.dataset.plan === p);
    });
    document.querySelector('input[name="plan"][value="' + p + '"]').checked = true;
}

paypal_sdk.Buttons({
    createOrder: function(data, actions) {
        const planData = ${JSON.stringify(PLANS)};
        const p = planData[selectedPlan];
        return actions.order.create({
            purchase_units: [{
                description: \`${PRODUCT_NAME} - \${p.label}\`,
                amount: { value: p.price }
            }],
            application_context: { shipping_preference: 'NO_SHIPPING' }
        });
    },
    onApprove: function(data, actions) {
        document.getElementById('paypal-button-container').innerHTML = '<div class="loading">Processing payment...</div>';
        return fetch('/api/capture-paypal-order', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                order_id: data.orderID,
                plan: selectedPlan
            })
        }).then(r => r.json()).then(result => {
            if (result.ok) {
                document.getElementById('checkout-view').classList.add('hidden');
                document.getElementById('license-key').textContent = result.key;
                document.getElementById('success-view').classList.remove('hidden');
            } else {
                document.getElementById('paypal-button-container').innerHTML =
                    '<div class="error">Payment failed: ' + (result.error || 'Unknown error') + '</div>';
            }
        }).catch(err => {
            document.getElementById('paypal-button-container').innerHTML =
                '<div class="error">Network error: ' + err.message + '</div>';
        });
    },
    onError: function(err) {
        const errorStr = err.toString();
        
        // Check if the user just closed the window manually
        if (errorStr.includes("Detected popup close")) {
            // Handle gracefully without breaking the layout
            console.log("User closed the checkout popup window.");
            return; 
        }
        
        // Keep this for actual fatal/network errors
        document.getElementById('paypal-button-container').innerHTML =
            '<div class="error">PayPal error: ' + errorStr + '</div>';
    }
}).render('#paypal-button-container');
</script>
</body>
</html>`;

    return new Response(html, {
        headers: {
            "Content-Type": "text/html; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
        },
    });
}

async function handleCaptureOrder(request, env) {
    if (request.method !== "POST") return json({ error: "POST required" }, 405);

    const { order_id, plan } = await request.json();
    if (!order_id) return json({ error: "order_id required" }, 400);

    let accessToken;
    try {
        accessToken = await getPayPalAccessToken(env);
    } catch (e) {
        return json({ error: "Failed to authenticate with PayPal", detail: e.message }, 500);
    }

    const captureResp = await fetch(`${PAYPAL_API}/v2/checkout/orders/${order_id}/capture`, {
        method: "POST",
        headers: {
            "Authorization": `Bearer ${accessToken}`,
            "Content-Type": "application/json",
        },
    });

    const captureData = await captureResp.json();

    if (captureData.status !== "COMPLETED") {
        return json({ error: "Payment not completed", status: captureData.status, detail: captureData }, 400);
    }

    const payer = captureData.payer;
    const purchaseUnit = captureData.purchase_units?.[0];
    const txnId = purchaseUnit?.payments?.captures?.[0]?.id || order_id;
    const email = payer?.email_address || "unknown";
    const payerName = payer?.name?.given_name
        ? `${payer.name.given_name} ${payer.name.surname || ""}`.trim()
        : "unknown";

    const existing = await env.DB.prepare("SELECT key FROM licenses WHERE txn_id = ?").bind(txnId).first();
    if (existing) return json({ ok: true, key: existing.key });

    const key = generateKey();

    await env.DB.prepare(
        "INSERT INTO licenses (key, email, payer_name, txn_id, plan, max_activations, created_at) VALUES (?, ?, ?, ?, ?, 3, datetime('now'))"
    ).bind(key, email, payerName, txnId, plan || "monthly").run();

    const sent = await sendLicenseEmail(email, key, plan);
    if (!sent) console.error(`Failed to send email to ${email} for key ${key}`);

    return json({ ok: true, key, emailed: sent });
}

// ── Main ─────────────────────────────────────────────────────────

export default {
    async fetch(request, env) {
        if (request.method === "OPTIONS") {
            return new Response(null, { headers: corsHeaders() });
        }

        const url = new URL(request.url);
        const path = url.pathname;

        if (path === "/" || path === "/checkout") {
            return serveCheckoutPage(request);
        }

        if (path === "/api/ping") {
            return json({ ok: true });
        }

        if (path === "/api/capture-paypal-order") {
            return handleCaptureOrder(request, env);
        }

        if (path === "/api/paypal-ipn") {
            if (request.method !== "POST") return json({ error: "POST required" }, 405);
            const body = await request.text();
            const params = formDataToObject(body);

            const verified = await verifyIPN(body);
            if (!verified) return json({ error: "IPN verification failed" }, 400);

            if (params.payment_status !== "Completed") return json({ ok: true, info: "not completed" });
            if (params.txn_type !== "web_accept" && params.txn_type !== "subscr_payment") return json({ ok: true, info: "ignored txn_type" });

            const existing = await env.DB.prepare("SELECT key FROM licenses WHERE txn_id = ?").bind(params.txn_id).first();
            if (existing) return json({ ok: true, info: "duplicate" });

            const key = generateKey();
            const email = params.payer_email || "unknown";
            const payerName = `${params.first_name || ""} ${params.last_name || ""}`.trim();

            await env.DB.prepare(
                "INSERT INTO licenses (key, email, payer_name, txn_id, plan, max_activations, created_at) VALUES (?, ?, ?, ?, 'ipn', 3, datetime('now'))"
            ).bind(key, email, payerName, params.txn_id).run();

            const sent = await sendLicenseEmail(email, key, "monthly");
            if (!sent) console.error(`Failed to send email to ${email} for key ${key}`);

            return json({ ok: true, key, emailed: sent });
        }

        if (path === "/api/validate") {
            const key = url.searchParams.get("key");
            const machine = url.searchParams.get("machine");
            const machineName = url.searchParams.get("name") || "";

            if (!key || !machine) return json({ error: "key and machine required" }, 400);

            const license = await env.DB.prepare("SELECT * FROM licenses WHERE key = ?").bind(key).first();
            if (!license) return json({ valid: false, error: "invalid_key" });

            if (license.expires_at && new Date(license.expires_at) < new Date()) {
                return json({ valid: false, error: "expired", expires_at: license.expires_at });
            }

            const existingActivation = await env.DB.prepare(
                "SELECT * FROM activations WHERE license_key = ? AND machine_id = ?"
            ).bind(key, machine).first();

            if (existingActivation) {
                const count = await env.DB.prepare("SELECT COUNT(*) as c FROM activations WHERE license_key = ?").bind(key).first();
                return json({ valid: true, already_activated: true, activation_count: count.c, max_activations: license.max_activations });
            }

            const count = await env.DB.prepare("SELECT COUNT(*) as c FROM activations WHERE license_key = ?").bind(key).first();
            if (count.c >= license.max_activations) {
                return json({ valid: false, error: "max_activations_reached", activation_count: count.c, max_activations: license.max_activations });
            }

            await env.DB.prepare(
                "INSERT INTO activations (license_key, machine_id, machine_name, activated_at) VALUES (?, ?, ?, datetime('now'))"
            ).bind(key, machine, machineName).run();

            const newCount = await env.DB.prepare("SELECT COUNT(*) as c FROM activations WHERE license_key = ?").bind(key).first();
            return json({ valid: true, already_activated: false, activation_count: newCount.c, max_activations: license.max_activations });
        }

        if (path === "/api/deactivate") {
            if (request.method !== "POST") return json({ error: "POST required" }, 405);
            const { key, machine } = await request.json();
            if (!key || !machine) return json({ error: "key and machine required" }, 400);

            const result = await env.DB.prepare(
                "DELETE FROM activations WHERE license_key = ? AND machine_id = ?"
            ).bind(key, machine).run();

            return json({ ok: true, deactivated: result.meta.changes > 0 });
        }

        if (path === "/api/status") {
            const key = url.searchParams.get("key");
            if (!key) return json({ error: "key required" }, 400);

            const license = await env.DB.prepare("SELECT * FROM licenses WHERE key = ?").bind(key).first();
            if (!license) return json({ valid: false, error: "invalid_key" });

            const activations = await env.DB.prepare(
                "SELECT machine_id, machine_name, activated_at FROM activations WHERE license_key = ? ORDER BY activated_at"
            ).bind(key).all();

            return json({
                valid: true,
                key: license.key,
                email: license.email,
                plan: license.plan,
                created_at: license.created_at,
                expires_at: license.expires_at,
                max_activations: license.max_activations,
                activation_count: activations.results.length,
                activations: activations.results,
            });
        }

        return json({ error: "not found" }, 404);
    },
};

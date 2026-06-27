const PAYPAL_IPN_URL = "https://ipnpb.paypal.com/cgi-bin/webscr";
const PAYPAL_SANDBOX_IPN_URL = "https://ipnpb.sandbox.paypal.com/cgi-bin/webscr";

const FROM_EMAIL = "licensing@usayeed.com";
const FROM_NAME = "Usayeed AI Companion";
const PRODUCT_NAME = "Usayeed AI Companion";
const BUY_LINK = "https://www.paypal.com/buy/..." // TODO: fill after creating button

function generateKey() {
    const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    const seg = () => Array.from({ length: 4 }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
    return `USYD-${seg()}-${seg()}-${seg()}`;
}

function json(data, status = 200) {
    return new Response(JSON.stringify(data), {
        status,
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
    });
}

function formDataToObject(body) {
    const params = new URLSearchParams(body);
    const obj = {};
    for (const [k, v] of params) obj[k] = v;
    return obj;
}

async function verifyIPN(body) {
    const verificationBody = `cmd=_notify-validate&${body}`;
    const resp = await fetch(PAYPAL_IPN_URL, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: verificationBody,
    });
    const text = await resp.text();
    return text === "VERIFIED";
}

async function sendLicenseEmail(email, licenseKey) {
    const body = `Thank you for purchasing ${PRODUCT_NAME}!

Your license key: ${licenseKey}

To activate:
1. Open FreeCAD and switch to the AI Companion workbench
2. Click Settings (gear icon)
3. Go to the "License" section
4. Enter your license key and click Activate

You can activate up to 3 machines with this key.

Need help? Reply to this email or visit our support page.

Thank you,
${FROM_NAME}`;

    const resp = await fetch("https://api.mailchannels.net/tx/v1/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            personalizations: [{ to: [{ email }] }],
            from: { email: FROM_EMAIL, name: FROM_NAME },
            subject: `Your ${PRODUCT_NAME} License Key`,
            content: [{ type: "text/plain", value: body }],
        }),
    });
    return resp.ok;
}

function corsHeaders() {
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    };
}

export default {
    async fetch(request, env) {
        if (request.method === "OPTIONS") {
            return new Response(null, { headers: corsHeaders() });
        }

        const url = new URL(request.url);
        const path = url.pathname;

        if (path === "/api/ping") {
            return json({ ok: true });
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
                "INSERT INTO licenses (key, email, payer_name, txn_id, max_activations, created_at) VALUES (?, ?, ?, ?, 3, datetime('now'))"
            ).bind(key, email, payerName, params.txn_id).run();

            const sent = await sendLicenseEmail(email, key);
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
                return json({
                    valid: true,
                    already_activated: true,
                    activation_count: count.c,
                    max_activations: license.max_activations,
                });
            }

            const count = await env.DB.prepare("SELECT COUNT(*) as c FROM activations WHERE license_key = ?").bind(key).first();
            if (count.c >= license.max_activations) {
                return json({
                    valid: false,
                    error: "max_activations_reached",
                    activation_count: count.c,
                    max_activations: license.max_activations,
                });
            }

            await env.DB.prepare(
                "INSERT INTO activations (license_key, machine_id, machine_name, activated_at) VALUES (?, ?, ?, datetime('now'))"
            ).bind(key, machine, machineName).run();

            const newCount = await env.DB.prepare("SELECT COUNT(*) as c FROM activations WHERE license_key = ?").bind(key).first();
            return json({
                valid: true,
                already_activated: false,
                activation_count: newCount.c,
                max_activations: license.max_activations,
            });
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

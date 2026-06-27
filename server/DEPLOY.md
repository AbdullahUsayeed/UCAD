# Deploy License Server to Cloudflare

## Option 1: Cloudflare Dashboard (no Node.js needed)

### 1. Create D1 Database
- Go to https://dash.cloudflare.com → Workers & Pages → D1
- Click "Create database"
- Name: `licensing-db`
- Go to the DB page → "Console" tab → paste contents of `src/schema.sql` → Run

### 2. Create Worker
- Go to Workers & Pages → "Create application" → "Create Worker"
- Name: `usayeed-licensing`
- Replace the code with contents of `src/index.js`
- Go to "Settings" → "Variables" → "D1 Database bindings"
- Variable name: `DB` → Database: `licensing-db`
- Go to "Settings" → "Variables" → "Secrets"
- Add secret: `PAYPAL_CLIENT_SECRET` = `EEUsyQuF9DZ8V-s__O2qx-w_9xMPawLi9ym78EpgY3ysEjfcTQ9hL0cY1gDWVFyrdIUJKLr--c25HvIn`
- Save and Deploy

### 3. Update licensing.py
Take the Worker URL (e.g. `https://usayeed-licensing.your-subdomain.workers.dev`)
and paste it into `orchestrator/licensing.py` line 17:
```python
SERVER_URL = "https://usayeed-licensing.your-subdomain.workers.dev"
```

## Option 2: CLI (requires Node.js)

```bash
cd server
npm install
npx wrangler d1 create licensing-db
# Copy the database_id output → paste into wrangler.toml
npx wrangler d1 execute licensing-db --file src/schema.sql
npx wrangler secret put PAYPAL_CLIENT_SECRET
# Paste your live PayPal Client Secret when prompted
npx wrangler deploy
```

## PayPal Setup for IPN (legacy — keep for compatibility)

If you also want PayPal hosted button IPN to work:

1. Go to https://www.paypal.com/buttons
2. Create a "Buy Now" button
3. Step 3: Check "Notify URL" → enter your Worker URL:
   `https://usayeed-licensing.your-subdomain.workers.dev/api/paypal-ipn`
4. Copy the button link for reference

## Email Setup (MailChannels)

Cloudflare Workers can send email via MailChannels for free.
1. The `FROM_EMAIL` in `src/index.js` must use a domain on your Cloudflare account
2. Add SPF record for your domain:
   ```
   v=spf1 include:relay.mailchannels.net ~all
   ```
3. Optionally add DKIM (see MailChannels docs)

## Verification

After deploying:
```bash
# Health check
curl https://usayeed-licensing.your-subdomain.workers.dev/api/ping
# Should return: {"ok":true}

# Checkout page
curl https://usayeed-licensing.your-subdomain.workers.dev/checkout
# Should return HTML checkout page
```

Then open the checkout URL in a browser and test a payment.

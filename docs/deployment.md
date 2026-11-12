# Deployment guide

This guide uses Vercel for the React/Vite static site, Render for FastAPI, MongoDB Atlas for persistence, Qdrant Cloud for optional semantic retrieval, and an SMTP-capable email provider. The same environment variables can be used on other hosts.

## 1. Prepare the source

1. Extract the ZIP and confirm local setup and tests pass.
2. Create a private Git repository and push the source. Do not commit `.env`, `.venv`, `node_modules`, API keys, or database credentials; `.gitignore` excludes local secrets and build output.
3. Configure a custom application domain if possible, for example `app.example.com` and `api.example.com`. Same-site subdomains make cookie configuration simpler.

## 2. Deploy the frontend

In Vercel, import the repository and set the project root to `frontend`.

- Build command: `npm run build`
- Output directory: `dist`
- Build environment variable: `VITE_API_URL=https://api.example.com`

`VITE_API_URL` is public browser configuration; never place a secret under a `VITE_` name. Rebuild the frontend after changing it. See the [Vite-on-Vercel guide](https://vercel.com/docs/frameworks/frontend/vite) and [Vite environment-variable guide](https://vite.dev/guide/env-and-mode.html).

## 3. Deploy the FastAPI backend

Create a Render Web Service from the same repository and set its root directory to `backend`.

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Python runtime: 3.11 or newer

Set these backend environment values in the host's secret/configuration panel:

```dotenv
DEMO_MODE=false
MONGODB_DATABASE=brandguard
MONGODB_URI=<Atlas application connection string>
JWT_SECRET=<random value at least 32 characters>
OTP_PEPPER=<different random value at least 32 characters>
JWT_ISSUER=brandguard-ai
SESSION_TTL_MINUTES=720
OTP_TTL_MINUTES=10
OTP_RESEND_COOLDOWN_SECONDS=60
OTP_MAX_ATTEMPTS=5
OTP_MAX_PER_HOUR=5
FRONTEND_ORIGIN=https://app.example.com
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
SMTP_HOST=<provider SMTP host>
SMTP_PORT=587
SMTP_USERNAME=<provider username>
SMTP_PASSWORD=<provider secret>
SMTP_FROM_EMAIL=<verified sender address>
SMTP_USE_SSL=false
```

Generate independent secrets locally with Python:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Run it twice and use a different value for each variable. Store both in Render's secret environment settings. Do not use the sample demo credentials in a deployed service.

If the app and API are on different registrable domains, configure `COOKIE_SAMESITE=none` with `COOKIE_SECURE=true` and HTTPS for both. The API also checks request origins against `FRONTEND_ORIGIN` and its local development origins. See the [Render FastAPI deployment guide](https://render.com/docs/deploy-fastapi).

## 4. Configure MongoDB Atlas

1. Create a cluster and a dedicated database user with access to the `brandguard` database.
2. Restrict network access to the backend's known egress IP or private network. Avoid opening database access to all IP addresses.
3. Copy Atlas's driver connection string into `MONGODB_URI`; replace its username, password, and database name using URL-encoded credentials as required.
4. Keep the URI only in the backend environment. Atlas connection strings use TLS and authenticate through the database user.
5. Deploy/restart the backend and check `GET /api/health` for `storage_mode: mongodb`.

Use the [Atlas client-library connection guide](https://www.mongodb.com/docs/atlas/driver-connection/) and [Atlas connection troubleshooting](https://www.mongodb.com/docs/atlas/troubleshoot-connection/).

## 5. Configure SMTP email delivery

Use credentials from an SMTP-capable transactional email provider and a sender/domain that the provider has verified. For STARTTLS use port 587 with `SMTP_USE_SSL=false`; for SSL use the provider's SSL port (often 465) with `SMTP_USE_SSL=true`. Never expose SMTP variables to the frontend. Test registration and login against a real mailbox before inviting users.

## 6. Enable optional Gemini review

Set `GEMINI_API_KEY` and `GEMINI_MODEL` on the backend only, install `backend/requirements-ai.txt` as part of the backend build, and restart. The frontend asks the reviewer to opt in for each check. If a key is absent, deterministic checks and source retrieval continue to work.

## 7. Enable optional Qdrant RAG

1. Create a Qdrant Cloud cluster and a database API key with only the needed collection permissions.
2. Set `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`, and `QDRANT_EMBED_MODEL` in the backend environment.
3. Install `backend/requirements-rag.txt` during the backend build. FastEmbed runs the embedding model locally; the first request downloads the model. Ensure the service can reach the model download host and has enough disk/RAM.
4. Run a content check, inspect its cited sources, and verify the health endpoint reports Qdrant configured.

See the [Qdrant Cloud quickstart](https://qdrant.tech/documentation/cloud-quickstart/), [Qdrant API key guide](https://qdrant.tech/documentation/cloud/authentication/), and [FastEmbed model guide](https://qdrant.tech/documentation/embeddings/fastembed/). Qdrant is optional: if it cannot be reached, the service falls back to lexical retrieval.

## 8. First launch and checks

1. Visit the frontend and register the first account for the organization. That account is the organization administrator.
2. Verify the email from its OTP, then sign in with the password and the separate login OTP.
3. Add approved guidelines and facts before inviting creators.
4. Submit a test draft, inspect each evidence citation, clear findings, approve it as a reviewer, and publish it.
5. Submit a rule proposal from the review screen and verify that it stays pending until an administrator approves it.
6. Check the backend's `/docs` and `/api/health` endpoints. Run the test suite as part of release validation.

Do not use the development mailbox in production; it returns 404 whenever `DEMO_MODE=false`.

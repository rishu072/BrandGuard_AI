# BrandGuard AI

BrandGuard AI helps teams catch brand and content risks before publication. Creators submit a draft, deterministic checks and optional RAG/LLM review compare it with approved sources, a human reviewer makes the decision, and an administrator controls any changes to the rules.

**Stack:** React 19, Vite, Tailwind CSS 4, FastAPI, MongoDB, optional Gemini, optional Qdrant + FastEmbed.

## What is included

- Email registration and verified-email activation, password sign-in followed by an emailed one-time code, logout, expiring JWT sessions, and role-based access.
- OTP hashes, expiry, one-time use, resend cooldowns, attempt caps, hourly delivery limits, and SMTP email delivery. Demo mode uses a local-only demo mailbox instead of exposing codes in API responses or logs.
- Organization-scoped workspaces. Each organization has its own approved sources, facts, terminology, drafts, findings, decisions, audit trail, and rule proposals.
- Creator, reviewer, and administrator roles enforced by the FastAPI service.
- A protected administrator dashboard for member access, organization details, approved brand sources, facts, terminology, submissions, and rule-improvement proposals.
- Deterministic compliance checks, evidence-backed lexical retrieval, optional Qdrant vector retrieval, and optional Gemini analysis. AI findings are accepted only when they cite a retrieved approved source and quote text from the draft.
- A publication gate: reviewers cannot approve drafts with unresolved critical/high findings, and publication requires human approval plus resolution or dismissal of every finding.
- Feedback is saved as a pending proposal. Only an explicit administrator approval adds that proposed text to the approved library.
- Seeded offline demo workspace and an environment-configured demo administrator.
- Authentication and workflow tests, OpenAPI docs, deployment notes, and a security checklist.

## Quick start on Windows

Requirements: Python 3.11 or newer, Node.js 22 or newer, and PowerShell.

1. Extract the ZIP and open PowerShell in the `brandguard-ai` project folder.
2. Create the environment file and Python environment:

   ```powershell
   Copy-Item .env.example .env
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r backend\requirements.txt
   ```

3. Start the API in the first terminal:

   ```powershell
   cd backend
   uvicorn app.main:app --reload
   ```

   The API runs at `http://localhost:8000`; interactive docs are at `http://localhost:8000/docs`.

4. Start the frontend in a second terminal, from the project folder:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

5. Open `http://localhost:5173`.

### Demo sign-in

The example `.env` seeds this administrator on first launch:

- Email: `admin@brandguard.local`
- Password: `ChangeThisDemo123!`

After entering the email and password, choose **Open local demo mailbox** to get the login code. The local mailbox endpoint is disabled outside demo mode and is only available to a local development client. Change the sample password in `.env` before sharing the demo or deploying it.

New registrations create a separate organization; its first account becomes that organization’s administrator. In demo mode, verification codes are available only through the local mailbox. With SMTP configured, codes are sent to the registered address.

## Database setup

The default `DEMO_MODE=true` stores data in memory and requires no MongoDB or paid credentials. State resets when the backend restarts.

For local MongoDB persistence, Docker Desktop is required:

1. In `.env`, set unique local MongoDB credentials using `MONGO_INITDB_ROOT_USERNAME` and `MONGO_INITDB_ROOT_PASSWORD`.
2. Start MongoDB, which binds only to the local machine:

   ```powershell
   docker compose up -d mongodb
   ```

3. Set `DEMO_MODE=false`, set `MONGODB_URI` to the authenticated local URI, and set strong random `JWT_SECRET` and `OTP_PEPPER` values (at least 32 characters each).
4. Configure SMTP before starting the backend. In persistent mode, the service fails closed if MongoDB or SMTP is not configured.
5. Register the first account for an organization; it becomes that organization’s administrator.

Example local MongoDB URI (use your own credentials):

```text
mongodb://brandguard:ChangeMeMongo2026@localhost:27017/?authSource=admin
```

The Compose MongoDB service is for local development only. For deployment, use a managed MongoDB deployment with a least-privilege database user, TLS, and an IP/network access list. See [docs/deployment.md](docs/deployment.md).

## Email OTP configuration

SMTP is configured only in the backend `.env`; never put mail credentials in Vite variables. For standard STARTTLS SMTP, set:

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp-user
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_EMAIL=brandguard@example.com
SMTP_USE_SSL=false
```

For an SSL SMTP endpoint, use its SSL port (commonly 465) and set `SMTP_USE_SSL=true`. Transactional email services that provide SMTP credentials can use the same settings. Verify sender/domain authentication with your email provider. Demo mode works without SMTP through the local mailbox; production mode requires SMTP.

## Optional AI and RAG

### Gemini

Leave `GEMINI_API_KEY` blank for offline deterministic checks. To enable the server-side Gemini adapter:

```powershell
pip install -r backend\requirements-ai.txt
```

Set `GEMINI_API_KEY` and `GEMINI_MODEL` in the backend `.env`, restart the API, then opt in to Gemini for an individual review. The draft and retrieved approved excerpts are sent to Google only for that opted-in review. Gemini does not approve or publish content. Use the [Gemini API documentation](https://ai.google.dev/gemini-api/docs) to create/configure a key.

### Qdrant

Without Qdrant, retrieval uses approved-source lexical matching. For local Qdrant, install the optional packages and start its local-only Compose profile:

```powershell
pip install -r backend\requirements-rag.txt
docker compose --profile rag up -d qdrant
```

Set `QDRANT_URL=http://localhost:6333` in `.env` and restart the API. The first vector search downloads the configured local FastEmbed model. No embedding provider account is required. If Qdrant or its optional packages are unavailable, the review falls back to lexical retrieval. For Qdrant Cloud, set the cluster URL and API key; see the [Qdrant Cloud quickstart](https://qdrant.tech/documentation/cloud-quickstart/) and [FastEmbed model guide](https://qdrant.tech/documentation/embeddings/fastembed/).

## Tests and production build

From the project root after installing dependencies:

```powershell
pip install -r backend\requirements-test.txt
python -m pytest backend\tests -q
```

Build the frontend:

```powershell
cd frontend
npm run build
```

The authentication tests cover Argon2 password hashing, email verification, OTP hashing/expiry/one-time use, attempt caps, resend cooldowns, and logout. Workflow tests cover server-side role checks, admin-reviewed rule proposals, organization workspace isolation through the data model, reviewer approval checks, and the publication gate.

## API overview

| Method | Route | Access | Purpose |
| --- | --- | --- | --- |
| POST | `/api/auth/register` | Public | Create an organization and send email verification OTP |
| POST | `/api/auth/login` | Public | Check password and send login OTP |
| POST | `/api/auth/verify` | Public | Verify one-time code and issue session cookie |
| POST | `/api/auth/resend` | Public | Resend eligible OTP under cooldown/rate limits |
| GET | `/api/auth/me` | Signed in | Read current user and organization |
| POST | `/api/auth/logout` | Signed in | Revoke current session |
| GET/POST | `/api/drafts` | Member+ | List or create content submissions |
| POST | `/api/drafts/{id}/audit` | Member+ | Run rules, retrieval, and optional Gemini analysis |
| POST | `/api/drafts/{id}/submit-review` | Member+ | Enter human review queue |
| POST | `/api/drafts/{id}/review` | Reviewer/admin | Approve or request changes |
| POST | `/api/drafts/{id}/publish` | Reviewer/admin | Publish after all required gates pass |
| POST | `/api/rule-proposals` | Member+ | Submit feedback for admin review |
| GET/PATCH | `/api/admin/dashboard`, `/api/admin/users/{id}` | Admin | Manage organization members and inspect governance |
| POST | `/api/admin/proposals/{id}/decision` | Admin | Approve/reject a proposed rule change |

Full OpenAPI/Swagger documentation: `http://localhost:8000/docs`. More endpoint detail is in [docs/api.md](docs/api.md).

## Deployment

See [docs/deployment.md](docs/deployment.md) for a concrete frontend/backend/database/vector-store/email setup. A typical split deployment uses a static Vite frontend, a FastAPI web service, managed MongoDB, optional Qdrant, and an SMTP-capable transactional email provider.

## Security checklist

- Set `DEMO_MODE=false`; remove/change demo environment values and never deploy the example credentials.
- Use strong independent `JWT_SECRET` and `OTP_PEPPER` values, keep all secrets in the backend secret manager, and rotate them if exposed.
- Use a managed MongoDB service with TLS, least-privilege credentials, backups, and restricted network access.
- Set `COOKIE_SECURE=true` in HTTPS deployment. For a cross-site frontend/API pair use `COOKIE_SAMESITE=none` and HTTPS; set `FRONTEND_ORIGIN` to the exact frontend origin.
- Configure authenticated SMTP and verify sender-domain policy. OTPs are short-lived and stored as HMAC hashes; codes never appear in API responses or server logs.
- Keep Qdrant and MongoDB private. Never include their credentials or Gemini keys in frontend environment variables.
- Review every finding and proposed rule change. Only reviewers publish, and only admins apply proposed rules.
- Before production, place the API behind a trusted HTTPS proxy and use a shared/distributed IP rate limiter if running multiple backend instances.

For detail see [docs/security.md](docs/security.md). This is a hackathon MVP: it does not parse uploaded PDFs, inspect visual assets, provide password recovery, or replace legal/compliance review. Organization workspaces are separated; verify provider/network settings and run the included tests before deployment.

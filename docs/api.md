# API reference

The running service provides Swagger UI at `http://localhost:8000/docs`, ReDoc at `/redoc`, and its OpenAPI schema at `/openapi.json`.

## Authentication flow

1. `POST /api/auth/register` with `email`, `password`, `name`, and `organization_name`. The first account is an administrator for its new organization. A verification code is sent by SMTP or placed in the demo mailbox.
2. `POST /api/auth/verify` with `email`, `purpose: "verify_email"`, and the six-digit `code`. The response sets the HTTP-only `brandguard_session` cookie.
3. Later, `POST /api/auth/login` with email/password. It sends an OTP with `purpose: "login"` and does not issue a session yet.
4. `POST /api/auth/verify` with the login purpose/code issues the authenticated session.
5. `GET /api/auth/me` returns the active user and organization. `POST /api/auth/logout` revokes the current session and clears the cookie.

The local demo mailbox is `GET /api/dev/mailbox?email=...`. It only works when `DEMO_MODE=true` and the client is local. Production always uses SMTP.

OTP configuration: `OTP_TTL_MINUTES`, `OTP_RESEND_COOLDOWN_SECONDS`, `OTP_MAX_ATTEMPTS`, and `OTP_MAX_PER_HOUR`. Passwords must have at least 10 characters, including a lowercase letter, uppercase letter, and number. API sessions use an HTTP-only, secure-in-production cookie.

## Access levels

| Role | Allowed actions |
| --- | --- |
| Member | Create/check drafts, apply or dismiss suggestions, submit for review, read approved knowledge, propose rule changes |
| Reviewer | Member actions plus review queue, approve/request changes, publish after gates pass |
| Admin | Reviewer actions plus organization/member administration and approved knowledge/rule management |

All authorization is checked by the backend and scoped to the session's organization.

## Core endpoints

| Method | Route | Access | Purpose |
| --- | --- | --- | --- |
| GET | `/api/health` | Public | Storage and optional provider configuration state |
| GET | `/api/dashboard` | Member+ | Current organization metrics, drafts, and events |
| GET | `/api/brand-library` | Member+ | Approved sources, facts, terminology, and asset metadata |
| POST | `/api/brand-library/sources` | Admin | Add approved guideline/source text |
| POST | `/api/brand-library/facts` | Admin | Add an approved fact with evidence excerpt |
| POST | `/api/brand-library/terminology` | Admin | Add preferred/avoided terminology |
| GET / POST | `/api/drafts` | Member+ | List or create drafts |
| GET | `/api/drafts/{id}` | Member+ | Read a draft/report in the current organization |
| POST | `/api/drafts/{id}/audit` | Member+ | Run checks and retrieval; body `{ "include_ai": true }` opts in to Gemini |
| PATCH | `/api/drafts/{id}/findings/{finding_id}` | Member+ | Accept, edit, or dismiss a finding |
| POST | `/api/drafts/{id}/submit-review` | Member+ | Move a checked draft into human review |
| GET | `/api/review-queue` | Reviewer/admin | Read the review queue |
| POST | `/api/drafts/{id}/review` | Reviewer/admin | Body includes `action: "approved"` or `"changes_requested"` and an optional comment |
| POST | `/api/drafts/{id}/publish` | Reviewer/admin | Publish only after approval and resolving every open finding |
| GET | `/api/audit-log` | Member+ | Read current-organization activity |
| GET | `/api/analytics` | Member+ | Current workspace counts and recent activity |
| POST | `/api/rule-proposals` | Member+ | Submit feedback for an administrator; does not change rules |
| GET | `/api/admin/dashboard` | Admin | Organization, users, proposals, submissions, and knowledge summary |
| POST | `/api/admin/users` | Admin | Invite an organization user with role and temporary password |
| PATCH | `/api/admin/users/{id}` | Admin | Change role or active access; cannot remove the last active admin |
| PATCH | `/api/admin/organization` | Admin | Update organization profile |
| GET | `/api/admin/proposals` | Admin | List rule improvement proposals |
| POST | `/api/admin/proposals/{id}/decision` | Admin | Approve/reject proposal; approval explicitly adds a source to the active library |

API error responses use standard HTTP status codes and a `detail` message. Protected routes return `401` for an absent/expired session, `403` for insufficient role, and `404` when a requested record is not in the caller's organization.

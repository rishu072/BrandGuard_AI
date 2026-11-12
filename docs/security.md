# Security notes and deployment checklist

## Authentication

- Passwords are hashed with Argon2id using the `argon2-cffi` library; password hashes are never returned by API routes.
- Registration remains inactive until email verification. Password login always sends a separate one-time login code.
- OTP codes are generated with a cryptographic random generator, stored as HMAC-SHA256 hashes keyed by `OTP_PEPPER`, expire after the configured TTL, allow a capped number of attempts, and are deleted after successful use.
- Resends have a cooldown and an hourly per-email limit. MongoDB mode persists OTP-send timestamps. Authentication routes also apply per-process IP/email sliding-window limits.
- Sessions use signed JWTs in an HTTP-only cookie and a server-side session record. Logout revokes the current session; deactivated users and role changes take effect on the next request.
- Demo OTPs are held in an in-memory local mailbox. The endpoint is disabled outside demo mode and checks that the request came from a local development client. Production never returns OTPs in API responses or logs.

## Authorization and publication

- User, reviewer, and administrator access is checked by backend dependencies. Hiding a button in React is not treated as authorization.
- Every workspace load uses the authenticated user's organization ID. Clients cannot choose an organization ID on protected endpoints.
- Only administrators can manage members and approved knowledge or decide rule proposals. Any member may submit a proposal for review.
- Reviewers cannot approve with unresolved critical or high findings. Publishing requires an approved decision and zero open findings.
- Feedback creates a proposal with pending status. It has no effect on the approved library until an administrator approves it.
- AI reports do not make workflow decisions. Gemini findings must quote text from the draft and cite a retrieved approved source; invalid citations are discarded.

## Before production

- Set `DEMO_MODE=false`. Never deploy the `.env.example` demo account; set any demo credentials only as private configuration and rotate them before sharing.
- Set two unrelated random secrets: `JWT_SECRET` and `OTP_PEPPER`, each at least 32 characters. Keep them in the host's secret manager and rotate after a suspected exposure. Rotating either invalidates sessions or pending OTP verification.
- Use HTTPS. Set `COOKIE_SECURE=true`. Use `COOKIE_SAMESITE=none` only when frontend and API are genuinely cross-site; keep `FRONTEND_ORIGIN` exact.
- Use MongoDB authentication, TLS, least-privilege database credentials, backups, and restricted network access. Keep MongoDB and Qdrant private.
- Configure SMTP sender authentication, rate limits, and abuse monitoring. Verify messages reach intended users before launch.
- Set provider quotas and privacy notices before enabling Gemini. The user-facing opt-in sends the draft and retrieved evidence to Google.
- Add distributed IP rate limiting at the gateway when deploying multiple API workers. The included IP limiter is process-local; per-email OTP cooldown/hourly limits are persisted with MongoDB.
- Review retention periods for content, email addresses, OTP request metadata, and audit records. The sample workspace keeps a bounded audit history; production retention policy should match organizational requirements.
- Monitor `/api/health`, backend logs, SMTP failures, database connectivity, and Qdrant latency. Never log passwords, OTP codes, JWTs, database URIs, or provider API keys.
- Run `pytest backend/tests -q` and `npm run build` before each release.

## Known MVP limits

- No password reset, self-service password change, passkeys, SSO, or session-management UI is included.
- Auth IP rate limits are local to one process. A shared limiter is needed for horizontally scaled production deployments.
- Workspace data is stored as one document per organization; split it into separate collections before large-scale use.
- Local Compose services are development-only, bound to loopback. They are not production database deployments.

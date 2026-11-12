# Architecture

## Request flow

1. A user registers with an email, password, name, and organization. Their first account is the organization's administrator.
2. FastAPI creates an unverified account, hashes its password with Argon2, creates a random six-digit OTP, stores only an HMAC-SHA256 hash of the code, and emails the code through SMTP. Demo mode instead places the message in a loopback-only development mailbox.
3. Email verification activates the account and issues a signed, expiring JWT in an HTTP-only cookie. Password sign-in also requires an emailed OTP. Each request reloads the user's active role and checks the revocable server-side session record.
4. Every workspace request uses the authenticated organization ID. MongoDB stores a workspace per organization; demo mode keeps a workspace per organization in process memory.
5. A compliance check runs deterministic rules and retrieves only currently approved sources/facts. Retrieval uses Qdrant + local FastEmbed when configured and available, otherwise approved-source lexical matching.
6. If Gemini is explicitly enabled for that check, the backend sends the draft and retrieved evidence to Google. Findings are discarded unless the quoted excerpt appears in the draft and the citation title maps to a retrieved approved source. The model cannot decide whether to approve or publish.
7. A creator submits the checked draft for human review. Reviewers cannot approve while critical/high findings remain open. Publication requires an approved status and every finding resolved or dismissed.
8. User feedback becomes a pending rule proposal. Only an administrator decision can add approved text to the source library. Review decisions and administration actions are timestamped in the audit history.

## Main components

- `frontend/src/AuthScreen.jsx`: registration, password sign-in, OTP verification, resend, and local demo mailbox.
- `frontend/src/App.jsx`: the existing review workspace, updated to use the authenticated role.
- `frontend/src/AdminPage.jsx`: organization, member, guideline, fact, terminology, submission, and proposal controls.
- `backend/app/auth.py`: password hashing, OTP/session store, SMTP delivery, JWT cookie, and role dependencies.
- `backend/app/main.py`: authentication, organization-scoped workflow, admin APIs, and publication gates.
- `backend/app/repository.py`: seeded demo workspace and organization-keyed MongoDB persistence.
- `backend/app/audit.py`: deterministic checks, evidence retrieval, Gemini citation validation.
- `backend/app/vector.py`: optional Qdrant/FastEmbed indexing and semantic retrieval.

## Data boundaries

MongoDB stores `users`, `organizations`, `challenges`, `sessions`, OTP-send records, and one `workspaces` document per organization. The workspace holds approved sources/facts/terminology, content submissions, findings, rule proposals, and audit events. Organization IDs come from the authenticated session/user record; clients cannot select an arbitrary organization for protected routes.

The in-memory demo store is process-local and resets on restart. The included Compose MongoDB and Qdrant services bind to loopback and are for local development. Production must use secured managed services or private networking.

## Trust boundaries and limitations

- Review findings are advisory; human approval is required for publication.
- Optional Gemini analysis can be unavailable or incomplete. Every finding must cite retrieved evidence; no evidence means no generated finding.
- A Qdrant outage or missing optional package falls back to lexical retrieval. In a production deployment with Qdrant required, monitor that status instead of assuming vectors are active.
- IP rate limiting is process-local. OTP send cooldown and hourly per-email caps are persisted with MongoDB, but horizontally scaled deployments should also use a shared edge/API rate limiter.
- Workspace records are currently stored as one document per organization, which is appropriate for the MVP but should be split into collections for large organizations or long audit retention.

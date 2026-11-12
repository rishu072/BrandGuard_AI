from http.cookies import SimpleCookie
import uuid

from fastapi import Response
from fastapi.testclient import TestClient

from app.auth import auth_store, hash_password, issue_session
from app.main import app

client = TestClient(app)


def make_user(role="admin", organization_id=None):
    organization_id = organization_id or str(uuid.uuid4())
    auth_store.create_organization("Test organization", organization_id=organization_id)
    user = {
        "id": str(uuid.uuid4()),
        "email": f"{role}-{uuid.uuid4().hex}@example.com",
        "name": f"Test {role}",
        "password_hash": hash_password("SecureTest123!"),
        "role": role,
        "organization_id": organization_id,
        "email_verified": True,
        "active": True,
    }
    auth_store.create_user(user)
    return user


def signed_in_client(user):
    test_client = TestClient(app)
    response = Response()
    issue_session(user, response)
    parsed = SimpleCookie()
    parsed.load(response.headers["set-cookie"])
    test_client.cookies.set("brandguard_session", parsed["brandguard_session"].value)
    return test_client


def test_registration_email_verification_and_logout():
    email = f"signup-{uuid.uuid4().hex}@example.com"
    response = client.post("/api/auth/register", json={
        "email": email,
        "password": "SecureTest123!",
        "name": "New Member",
        "organization_name": "Demo Team",
    })
    assert response.status_code == 202
    mailbox = client.get("/api/dev/mailbox", params={"email": email})
    assert mailbox.status_code == 200
    code = mailbox.json()["messages"][-1]["code"]
    verified = client.post("/api/auth/verify", json={"email": email, "code": code, "purpose": "verify_email"})
    assert verified.status_code == 200
    assert verified.json()["user"]["email_verified"] is True
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_role_enforcement_and_admin_reviewed_rule_proposals():
    admin = make_user("admin")
    member = make_user("member", admin["organization_id"])
    admin_client = signed_in_client(admin)
    member_client = signed_in_client(member)

    assert member_client.get("/api/admin/dashboard").status_code == 403
    denied = member_client.post("/api/brand-library/sources", json={
        "title": "Should be denied",
        "type": "Guideline",
        "content": "Members cannot approve or create production guidance.",
    })
    assert denied.status_code == 403

    proposal = member_client.post("/api/rule-proposals", json={
        "title": "Clarify campaign dates",
        "proposed_text": "Include the campaign end date whenever a promotion is mentioned.",
        "rationale": "Reviewers need a clear expiry to prevent stale offers.",
    })
    assert proposal.status_code == 201
    proposal_id = proposal.json()["id"]
    decision = admin_client.post(f"/api/admin/proposals/{proposal_id}/decision", json={
        "decision": "approved",
        "comment": "Approved after checking the current policy.",
    })
    assert decision.status_code == 200
    sources = member_client.get("/api/brand-library").json()["sources"]
    assert any(item["title"] == "Clarify campaign dates" for item in sources)


def test_publication_requires_human_approval_and_resolved_findings():
    admin = make_user("admin")
    admin_client = signed_in_client(admin)
    safe = admin_client.post("/api/drafts", json={
        "title": "Safe launch note",
        "channel": "Email",
        "text": "A calm morning ritual with thoughtful, everyday care.",
    }).json()
    assert admin_client.post(f"/api/drafts/{safe['id']}/publish").status_code == 409
    assert admin_client.post(f"/api/drafts/{safe['id']}/audit", json={}).status_code == 200
    assert admin_client.post(f"/api/drafts/{safe['id']}/submit-review").status_code == 200
    assert admin_client.post(f"/api/drafts/{safe['id']}/review", json={"action": "approved"}).status_code == 200
    published = admin_client.post(f"/api/drafts/{safe['id']}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    risky = admin_client.post("/api/drafts", json={
        "title": "Unsupported offer",
        "channel": "Social",
        "text": "Get 90% off with our guaranteed cure today.",
    }).json()
    admin_client.post(f"/api/drafts/{risky['id']}/audit", json={})
    admin_client.post(f"/api/drafts/{risky['id']}/submit-review")
    blocked = admin_client.post(f"/api/drafts/{risky['id']}/review", json={"action": "approved"})
    assert blocked.status_code == 409


def test_organization_data_isolation():
    first_admin = make_user("admin")
    second_admin = make_user("admin")
    first_client = signed_in_client(first_admin)
    second_client = signed_in_client(second_admin)
    draft = first_client.post("/api/drafts", json={
        "title": "Private organization draft",
        "channel": "Email",
        "text": "A quiet note for our own community and customers.",
    }).json()
    assert second_client.get(f"/api/drafts/{draft['id']}").status_code == 404
    assert second_client.get("/api/drafts").json() == []

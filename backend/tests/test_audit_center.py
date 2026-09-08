"""
Audit / Activity center (phase brief FEATURE 11).

GET /api/v1/admin/audit is a read-only projection over the EXISTING
audit_logs table -- ADMIN only, filterable, paginated. It must not be a
second audit system: it only ever reads what services/audit.record_audit
already wrote.
"""
from conftest import bearer


def test_audit_center_lists_real_actions(client, admin_user, officer_user):
    _, admin_token = admin_user
    _, officer_token = officer_user
    # generate a few audited actions
    client.post("/api/v1/incidents", json={"title": "a"}, headers=bearer(officer_token))
    client.post("/api/v1/cases", json={"title": "c"}, headers=bearer(officer_token))

    page = client.get("/api/v1/admin/audit", headers=bearer(admin_token)).json()
    assert page["total"] >= 2
    actions = {r["action"] for r in page["items"]}
    assert "INCIDENT_CREATE" in actions
    assert "CASE_CREATE" in actions
    assert "INCIDENT_CREATE" in page["actions"]  # distinct-actions filter list
    # username is resolved for the actor
    inc_row = next(r for r in page["items"] if r["action"] == "INCIDENT_CREATE")
    assert inc_row["username"] == "test_officer"


def test_audit_center_filters_and_pagination(client, admin_user, officer_user):
    _, admin_token = admin_user
    _, officer_token = officer_user
    for i in range(4):
        client.post("/api/v1/incidents", json={"title": f"i{i}"}, headers=bearer(officer_token))

    only = client.get("/api/v1/admin/audit", params={"action": "INCIDENT_CREATE"},
                      headers=bearer(admin_token)).json()
    assert only["total"] == 4
    assert all(r["action"] == "INCIDENT_CREATE" for r in only["items"])

    paged = client.get("/api/v1/admin/audit",
                       params={"action": "INCIDENT_CREATE", "limit": 2, "offset": 0},
                       headers=bearer(admin_token)).json()
    assert len(paged["items"]) == 2 and paged["total"] == 4


def test_audit_center_is_admin_only(client, officer_user, operator_user):
    assert client.get("/api/v1/admin/audit", headers=bearer(officer_user[1])).status_code == 403
    assert client.get("/api/v1/admin/audit", headers=bearer(operator_user[1])).status_code == 403
    assert client.get("/api/v1/admin/audit").status_code == 401

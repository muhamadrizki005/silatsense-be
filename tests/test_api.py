import pytest

from app.main import app


RETIRED = [
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("GET", "/api/v1/auth/me"),
    ("GET", "/api/v1/profile"),
    ("PATCH", "/api/v1/profile"),
    ("GET", "/api/v1/movements"),
    ("GET", "/api/v1/evaluations"),
    ("POST", "/api/v1/evaluations"),
    ("GET", "/api/v1/evaluations/1"),
    ("GET", "/api/v1/coach/members"),
    ("GET", "/api/v1/coach/members/1"),
    ("GET", "/api/v1/coach/members/1/evaluations"),
    ("POST", "/api/v1/coach/evaluations/1/notes"),
]


@pytest.mark.parametrize("method,path", RETIRED)
def test_retired_routes_are_not_reachable(client, member, method, path):
    assert client.request(method, path, headers=member).status_code == 404


def test_openapi_exposes_only_current_contracts():
    schema = app.openapi()
    assert "/api/v1/auth/sign-up" in schema["paths"]
    assert "/api/v1/auth/sign-in" in schema["paths"]
    assert "/api/v1/member/sessions" in schema["paths"]
    assert "/api/v1/coach/roster" in schema["paths"]
    retired_schema_names = {
        "Register",
        "Credentials",
        "TokenOut",
        "UserOut",
        "ProfilePatch",
        "NoteCreate",
        "MovementOut",
        "NoteOut",
    }
    assert not retired_schema_names.intersection(schema["components"]["schemas"])
    for _, path in RETIRED:
        assert path not in schema["paths"]
    assert not any(
        path.startswith(
            (
                "/api/v1/evaluations",
                "/api/v1/coach/members",
                "/api/v1/coach/evaluations",
            )
        )
        for path in schema["paths"]
    )


def test_role_escalation_forbidden(client, member):
    assert client.get("/api/v1/coach/roster", headers=member).status_code == 403
    assert (
        client.patch(
            "/api/v1/member/profile",
            headers=member,
            json={"fullName": "Attacker", "role": "COACH"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/auth/sign-up",
            json={
                "fullName": "Attacker",
                "identifier": "bad@example.com",
                "password": "password123",
                "role": "COACH",
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/auth/refresh-session",
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )


def test_profile_duplicate_email_and_catalog(client, member):
    assert (
        client.patch(
            "/api/v1/member/profile",
            headers=member,
            json={"fullName": "Updated"},
        ).json()["fullName"]
        == "Updated"
    )
    assert (
        client.post(
            "/api/v1/auth/sign-up",
            json={
                "fullName": "Other",
                "identifier": "ONE@example.com",
                "password": "password123",
            },
        ).status_code
        == 409
    )
    assert (
        len(
            client.get("/api/v1/member/training-modules", headers=member).json()[
                "modules"
            ]
        )
        == 4
    )

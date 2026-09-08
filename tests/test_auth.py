"""Auth flow tests: login, protected routes, logout, CSRF (see docs/04-auth.md)."""

import re

from httpx import AsyncClient

from app.db.models import User


def _extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "csrf token not found in page"
    return match.group(1)


async def test_login_page_renders(client: AsyncClient) -> None:
    response = await client.get("/login")
    assert response.status_code == 200
    assert "csrf_token" in response.text


async def test_home_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


async def test_login_success_sets_session_cookie(client: AsyncClient, test_user: User) -> None:
    login_page = await client.get("/login")
    csrf_token = _extract_csrf(login_page.text)

    response = await client.post(
        "/login",
        data={"username": "alice", "password": "correct-horse-battery", "csrf_token": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "session" in response.cookies


async def test_login_wrong_password_rejected(client: AsyncClient, test_user: User) -> None:
    login_page = await client.get("/login")
    csrf_token = _extract_csrf(login_page.text)

    response = await client.post(
        "/login",
        data={"username": "alice", "password": "wrong-password", "csrf_token": csrf_token},
    )

    assert response.status_code == 401
    assert "session" not in response.cookies


async def test_login_bad_csrf_rejected(client: AsyncClient, test_user: User) -> None:
    await client.get("/login")

    response = await client.post(
        "/login",
        data={
            "username": "alice",
            "password": "correct-horse-battery",
            "csrf_token": "not-the-real-token",
        },
    )

    assert response.status_code == 401
    assert "session" not in response.cookies


async def test_full_login_home_logout_flow(client: AsyncClient, test_user: User) -> None:
    login_page = await client.get("/login")
    csrf_token = _extract_csrf(login_page.text)
    await client.post(
        "/login",
        data={"username": "alice", "password": "correct-horse-battery", "csrf_token": csrf_token},
    )

    home = await client.get("/", follow_redirects=False)
    assert home.status_code == 303
    assert home.headers["location"] == "/dashboard"

    dashboard = await client.get("/dashboard")
    assert dashboard.status_code == 200

    logout_csrf = _extract_csrf(dashboard.text)
    logout_response = await client.post(
        "/logout", data={"csrf_token": logout_csrf}, follow_redirects=False
    )
    assert logout_response.status_code == 303

    after_logout = await client.get("/", follow_redirects=False)
    assert after_logout.status_code == 303

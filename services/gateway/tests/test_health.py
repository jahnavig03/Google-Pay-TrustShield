async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_health_needs_no_role_header(client):
    assert (await client.get("/health")).status_code == 200


async def test_cors_allows_the_vite_dev_server(client):
    resp = await client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_origins_accept_both_separators(monkeypatch):
    """Semicolons for the Cloud Run deploy, commas for a local .env. Both must work."""
    from trustshield_gateway.settings import cors_allow_origins

    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://a.web.app;https://b.firebaseapp.com")
    assert cors_allow_origins() == ["https://a.web.app", "https://b.firebaseapp.com"]

    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:5173,http://localhost:4173")
    assert cors_allow_origins() == ["http://localhost:5173", "http://localhost:4173"]

    monkeypatch.setenv("CORS_ALLOW_ORIGINS", " https://a.web.app ; ; https://b.web.app ")
    assert cors_allow_origins() == ["https://a.web.app", "https://b.web.app"]

    monkeypatch.delenv("CORS_ALLOW_ORIGINS")
    assert cors_allow_origins() == ["http://localhost:5173"]

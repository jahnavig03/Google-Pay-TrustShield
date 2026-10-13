async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_health_needs_no_role_header(client):
    assert (await client.get("/health")).status_code == 200


async def test_cors_allows_the_vite_dev_server(client):
    resp = await client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"

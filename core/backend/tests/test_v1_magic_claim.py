def test_v1_magic_claim_route_registered(client):
    # too-short token → 400 invalid_token (same as /auth/magic), proving the
    # /v1/auth/magic-claim alias is wired for the /activate SPA page.
    r = client.get("/v1/auth/magic-claim?token=short")
    assert r.status_code == 400, r.text

def test_v1_magic_claim_unknown_token_404(client):
    r = client.get("/v1/auth/magic-claim?token=ThisTokenDoesNotExistAtAll1234567890")
    assert r.status_code == 404, r.text

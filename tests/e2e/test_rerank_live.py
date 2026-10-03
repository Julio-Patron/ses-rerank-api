import os
import time

import pytest
import requests

pytestmark = pytest.mark.integration

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
ADMIN_KEY = os.getenv("GATEWAY_ADMIN_KEY", "test_admin_key_12345678901234567890")

@pytest.fixture(scope="session")
def api_key():
    # Wait for the gateway to be ready
    for _ in range(10):
        try:
            res = requests.get(f"{GATEWAY_URL}/healthz")
            if res.status_code == 200:
                break
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(2)
    else:
        pytest.fail("Gateway did not become ready in time")

    # Create an API key using the admin endpoint
    headers = {"X-Admin-Key": ADMIN_KEY, "Content-Type": "application/json"}
    # Check if admin endpoint exists, in prompt it says:
    # Admin API key can be created via `/api/v1/admin/keys`
    payload = {"credits": 5000, "name": "e2e_test_key"}
    res = requests.post(f"{GATEWAY_URL}/api/v1/admin/keys", json=payload, headers=headers)
    if res.status_code != 200:
        # Maybe the endpoint is different or admin key is wrong
        # Let's try the signup endpoint instead
        res_signup = requests.post(f"{GATEWAY_URL}/v1/auth/signup", json={"email": "test@e2e.com", "name": "e2e"})
        if res_signup.status_code == 200:
            return res_signup.json()["api_key"]
        pytest.fail(f"Failed to create API key via admin or signup. Admin: {res.text}, Signup: {res_signup.text}")
    
    return res.json()["api_key"]

def test_healthz():
    res = requests.get(f"{GATEWAY_URL}/healthz")
    assert res.status_code == 200

def test_readyz():
    res = requests.get(f"{GATEWAY_URL}/readyz")
    assert res.status_code == 200

def test_rerank_live(api_key):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "query": "Which clause talks about termination?",
        "documents": [
            "The contract is valid for 5 years.",
            "Termination is allowed with 30 days notice.",
            "Payment is due on the 15th of every month."
        ],
        "top_n": 2
    }
    res = requests.post(f"{GATEWAY_URL}/v1/rerank", json=payload, headers=headers)
    assert res.status_code == 200, f"Rerank failed: {res.text}"
    
    data = res.json()
    assert "results" in data
    assert len(data["results"]) == 2
    
    # The most relevant document should be index 1
    assert data["results"][0]["index"] == 1
    assert data["results"][0]["relevance_score"] > 0.0

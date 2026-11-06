import unittest
import hmac
import os
import json
import tempfile
from pathlib import Path

class MockRequest:
    def __init__(self, headers, body_json):
        self.headers = headers
        self._body = body_json

    async def json(self):
        return self._body

def parse_env_file(filepath):
    """Standalone parser matching load_environment behavior in mesh/mesh/api.py."""
    loaded = {}
    if os.path.isfile(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k:
                    loaded[k] = v
    return loaded

def validate_auth(request, expected_token):
    if not expected_token:
        return 503, "MESH_PROMPT_TOKEN is not configured on the laptop"
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return 401, "Missing or malformed Authorization header"
    token = auth_header[7:].strip()
    if not hmac.compare_digest(token, expected_token):
        return 403, "Unauthorized: Invalid bearer token"
    return 200, "OK"

class TestMeshPromptAuth(unittest.TestCase):
    def test_missing_token_env(self):
        req = MockRequest({"Authorization": "Bearer secret123"}, {"prompt": "hello"})
        code, msg = validate_auth(req, None)
        self.assertEqual(code, 503)

    def test_missing_auth_header(self):
        req = MockRequest({}, {"prompt": "hello"})
        code, msg = validate_auth(req, "secret123")
        self.assertEqual(code, 401)

    def test_wrong_bearer_token(self):
        req = MockRequest({"Authorization": "Bearer wrong_token"}, {"prompt": "hello"})
        code, msg = validate_auth(req, "secret123")
        self.assertEqual(code, 403)

    def test_valid_bearer_token(self):
        req = MockRequest({"Authorization": "Bearer secret123"}, {"prompt": "hello"})
        code, msg = validate_auth(req, "secret123")
        self.assertEqual(code, 200)

    def test_token_distinction(self):
        # MESH_AGENT_TOKEN should not validate against MESH_PROMPT_TOKEN
        mesh_prompt_token = "prompt_secret_abc"
        mesh_agent_token = "agent_secret_xyz"
        req = MockRequest({"Authorization": f"Bearer {mesh_agent_token}"}, {"prompt": "hello"})
        code, _ = validate_auth(req, mesh_prompt_token)
        self.assertEqual(code, 403)

    def test_parse_env_file(self):
        with tempfile.NamedTemporaryFile("w+", delete=False) as f:
            f.write("# Comment\nMESH_PROMPT_TOKEN=my-secret-token\nMESH_AGENT_TOKEN=my-agent-token\n")
            f.flush()
            parsed = parse_env_file(f.name)
            self.assertEqual(parsed.get("MESH_PROMPT_TOKEN"), "my-secret-token")
            self.assertEqual(parsed.get("MESH_AGENT_TOKEN"), "my-agent-token")

if __name__ == "__main__":
    unittest.main()

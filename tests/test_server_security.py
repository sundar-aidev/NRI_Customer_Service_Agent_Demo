from __future__ import annotations

import base64
import inspect
import os
import unittest
from unittest.mock import patch

from serve import (
    Handler,
    PayloadTooLarge,
    Settings,
    validate_content_length,
    verify_basic_auth,
)


class ServerSecurityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(
            host="127.0.0.1",
            port=0,
            username="reviewer",
            password="a-secure-demo-password",
            auth_required=True,
        )

    def test_basic_auth_is_required_and_compared(self) -> None:
        self.assertFalse(verify_basic_auth(self.settings, ""))
        credential = base64.b64encode(b"reviewer:a-secure-demo-password").decode("ascii")
        self.assertTrue(verify_basic_auth(self.settings, f"Basic {credential}"))
        wrong = base64.b64encode(b"reviewer:wrong-password").decode("ascii")
        self.assertFalse(verify_basic_auth(self.settings, f"Basic {wrong}"))

    def test_healthcheck_is_the_only_explicit_public_route(self) -> None:
        dispatch_source = inspect.getsource(Handler._dispatch)
        self.assertIn('path != "/healthz"', dispatch_source)
        route_source = inspect.getsource(Handler._route)
        self.assertIn('path == "/healthz"', route_source)

    def test_custom_prompt_and_mutation_routes_are_absent(self) -> None:
        route_source = inspect.getsource(Handler._route)
        self.assertNotIn("/api/custom", route_source)
        self.assertNotIn("/api/knowledge/reset", route_source)
        self.assertNotIn("do_PUT", inspect.getsource(Handler))

    def test_request_body_limit_is_enforced(self) -> None:
        self.assertEqual(validate_content_length("10", 100), 10)
        with self.assertRaises(PayloadTooLarge):
            validate_content_length("101", 100)

    def test_hosted_password_minimum_is_six_characters(self) -> None:
        environment = {
            "NRI_REQUIRE_AUTH": "true",
            "NRI_DEMO_USERNAME": "reviewer",
            "NRI_DEMO_PASSWORD": "sixsix",
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = Settings.from_environment("0.0.0.0", 8080)
        self.assertEqual(settings.password, "sixsix")

    def test_hosted_password_shorter_than_six_is_rejected(self) -> None:
        environment = {
            "NRI_REQUIRE_AUTH": "true",
            "NRI_DEMO_USERNAME": "reviewer",
            "NRI_DEMO_PASSWORD": "short",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ValueError, "at least 6 characters"):
                Settings.from_environment("0.0.0.0", 8080)


if __name__ == "__main__":
    unittest.main()

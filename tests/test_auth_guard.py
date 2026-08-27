# -*- coding: utf-8 -*-
"""统一登录鉴权回归：令牌校验与停用账号拒绝。"""
import base64
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ.pop("QWENPAW_WORKING_DIR", None)
import importlib.util

spec = importlib.util.spec_from_file_location("auth_guard", Path(__file__).resolve().parents[1] / "backend" / "auth_guard.py")
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)


def _make_token(secret: str, sub: str = "u1") -> str:
    payload = json.dumps({"sub": sub, "iat": int(time.time()), "exp": int(time.time()) + 600, "jti": "t"}, ensure_ascii=False)
    b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    sig = hmac.new(secret.encode(), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


class AuthGuardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        env = Path(self._tmp.name)
        (env / "auth").mkdir()
        self.secret = "s" * 64
        (env / "auth" / "token_secret.txt").write_text(self.secret, encoding="utf-8")
        (env / "auth" / "users.json").write_text(json.dumps([
            {"username": "u1", "active": True},
            {"username": "u2", "active": False},
        ]), encoding="utf-8")
        os.environ["QWENPAW_WORKING_DIR"] = str(env)

    def tearDown(self):
        os.environ.pop("QWENPAW_WORKING_DIR", None)
        self._tmp.cleanup()

    def test_valid_token_accepted(self):
        self.assertEqual(main._verify_token_user("Bearer " + _make_token(self.secret)), "u1")

    def test_bad_signature_rejected(self):
        self.assertIsNone(main._verify_token_user("Bearer " + _make_token("wrong" * 8)))

    def test_expired_token_rejected(self):
        payload = json.dumps({"sub": "u1", "exp": int(time.time()) - 10})
        b64 = base64.urlsafe_b64encode(payload.encode()).decode("ascii")
        sig = hmac.new(self.secret.encode(), b64.encode("ascii"), hashlib.sha256).hexdigest()
        self.assertIsNone(main._verify_token_user(f"Bearer {b64}.{sig}"))

    def test_disabled_user_rejected(self):
        self.assertIsNone(main._verify_token_user("Bearer " + _make_token(self.secret, "u2")))

    def test_missing_token_rejected(self):
        self.assertIsNone(main._verify_token_user(""))
        self.assertIsNone(main._verify_token_user("Basic xyz"))


if __name__ == "__main__":
    unittest.main()

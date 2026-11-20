import os
import json
import tempfile
import unittest
from pathlib import Path

from post_on_telegram.credentials import resolve_credentials
from post_on_telegram.errors import ConfigError


class TestCredentials(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.credentials_file = Path(self.test_dir) / "credentials.json"
        self.original_env = os.environ.copy()

    def tearDown(self):
        for key in ["POST_ON_TELEGRAM_TOKEN", "POST_ON_TELEGRAM_CHAT_ID"]:
            if key in os.environ:
                del os.environ[key]
        os.environ.update(self.original_env)
        if self.credentials_file.exists():
            self.credentials_file.unlink()

    def _write_creds(self, data):
        self.credentials_file.write_text(json.dumps(data), encoding="utf-8-sig")

    def test_explicit_args(self):
        creds = resolve_credentials(token="test_token", chat_id="test_chat")
        self.assertEqual(creds["bot_token"], "test_token")
        self.assertEqual(creds["chat_id"], "test_chat")

    def test_env_vars(self):
        os.environ["POST_ON_TELEGRAM_TOKEN"] = "env_token:123456"
        os.environ["POST_ON_TELEGRAM_CHAT_ID"] = "env_chat"
        creds = resolve_credentials()
        self.assertEqual(creds["bot_token"], "env_token:123456")
        self.assertEqual(creds["chat_id"], "env_chat")

    def test_file_valid(self):
        self._write_creds({"bot_token": "file_token:123456", "chat_id": "file_chat"})
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds["bot_token"], "file_token:123456")
        self.assertEqual(creds["chat_id"], "file_chat")

    def test_file_legacy_aliases(self):
        self._write_creds({"telegram_token": "legacy_token:123456", "telegram_id": "legacy_chat"})
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds["bot_token"], "legacy_token:123456")
        self.assertEqual(creds["chat_id"], "legacy_chat")

    def test_file_missing_keys(self):
        self._write_creds({"bot_token": "partial_token"})
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds["bot_token"], "partial_token")
        self.assertEqual(creds["chat_id"], "")

    def test_file_invalid_json(self):
        self.credentials_file.write_text('{"invalid": json}', encoding="utf-8-sig")
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds, {})

    def test_file_not_dict(self):
        self.credentials_file.write_text("[]", encoding="utf-8-sig")
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds, {})

    def test_file_list(self):
        self.credentials_file.write_text("[1, 2, 3]", encoding="utf-8-sig")
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds, {})

    def test_file_missing_chat_id(self):
        self._write_creds({"bot_token": "token"})
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds["bot_token"], "token")
        self.assertEqual(creds["chat_id"], "")

    def test_file_missing_token(self):
        self._write_creds({"chat_id": "chat"})
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds["bot_token"], "")
        self.assertEqual(creds["chat_id"], "chat")

    def test_file_invalid_token(self):
        self._write_creds({"bot_token": "invalidtoken"})
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds["bot_token"], "invalidtoken")

    def test_strict_invalid_token(self):
        self._write_creds({"bot_token": "invalidtoken"})
        with self.assertRaises(ConfigError):
            resolve_credentials(credentials_file=str(self.credentials_file), strict=True)

    def test_strict_missing_chat_id(self):
        self._write_creds({"bot_token": "token"})
        with self.assertRaises(ConfigError):
            resolve_credentials(credentials_file=str(self.credentials_file), strict=True)

    def test_strict_missing_token(self):
        self._write_creds({"chat_id": "chat"})
        with self.assertRaises(ConfigError):
            resolve_credentials(credentials_file=str(self.credentials_file), strict=True)

    def test_strict_no_token_no_chat(self):
        self._write_creds({})
        with self.assertRaises(ConfigError):
            resolve_credentials(credentials_file=str(self.credentials_file), strict=True)

    def test_strict_invalid_json(self):
        self.credentials_file.write_text('{"invalid": json}', encoding="utf-8-sig")
        with self.assertRaises(ConfigError):
            resolve_credentials(credentials_file=str(self.credentials_file), strict=True)

    def test_strict_not_dict(self):
        self.credentials_file.write_text("[]", encoding="utf-8-sig")
        with self.assertRaises(ConfigError):
            resolve_credentials(credentials_file=str(self.credentials_file), strict=True)

    def test_strict_list(self):
        self.credentials_file.write_text("[1, 2, 3]", encoding="utf-8-sig")
        with self.assertRaises(ConfigError):
            resolve_credentials(credentials_file=str(self.credentials_file), strict=True)

    def test_strict_invalid_chat_id(self):
        self._write_creds({"bot_token": "token", "chat_id": ""})
        with self.assertRaises(ConfigError):
            resolve_credentials(credentials_file=str(self.credentials_file), strict=True)

    def test_explicit_args_precedence_over_file(self):
        self._write_creds({"bot_token": "file_token:123456", "chat_id": "file_chat"})
        creds = resolve_credentials(token="explicit_token:123456", chat_id="explicit_chat",
                                    credentials_file=str(self.credentials_file))
        self.assertEqual(creds["bot_token"], "explicit_token:123456")
        self.assertEqual(creds["chat_id"], "explicit_chat")

    def test_explicit_args_precedence_over_env(self):
        os.environ["POST_ON_TELEGRAM_TOKEN"] = "env_token:123456"
        os.environ["POST_ON_TELEGRAM_CHAT_ID"] = "env_chat"
        creds = resolve_credentials(token="explicit_token:123456", chat_id="explicit_chat")
        self.assertEqual(creds["bot_token"], "explicit_token:123456")
        self.assertEqual(creds["chat_id"], "explicit_chat")

    def test_file_precedence_over_env(self):
        self._write_creds({"bot_token": "file_token:123456", "chat_id": "file_chat"})
        os.environ["POST_ON_TELEGRAM_TOKEN"] = "env_token:123456"
        os.environ["POST_ON_TELEGRAM_CHAT_ID"] = "env_chat"
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds["bot_token"], "file_token:123456")
        self.assertEqual(creds["chat_id"], "file_chat")

    def test_int_chat_id(self):
        self._write_creds({"bot_token": "token:123456", "chat_id": 1234567890})
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds["chat_id"], "1234567890")

    def test_whitespace_stripped(self):
        self._write_creds({"bot_token": "  token:123456  ", "chat_id": "  chat  "})
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds["bot_token"], "token:123456")
        self.assertEqual(creds["chat_id"], "chat")

    def test_bom_handled(self):
        self.credentials_file.write_text('\ufeff{"bot_token": "token:123456", "chat_id": "chat"}', encoding="utf-8-sig")
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds["bot_token"], "token:123456")
        self.assertEqual(creds["chat_id"], "chat")

    def test_mask_token(self):
        from post_on_telegram.credentials import _mask_token
        self.assertEqual(_mask_token("123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq"), "123…opq")
        self.assertEqual(_mask_token("short"), "*****")
        self.assertEqual(_mask_token(""), "")

    def test_no_token_no_chat_returns_empty(self):
        creds = resolve_credentials()
        self.assertEqual(creds, {})

    def test_token_without_colon(self):
        creds = resolve_credentials(token="invalidtoken", chat_id="chat")
        self.assertEqual(creds["bot_token"], "invalidtoken")
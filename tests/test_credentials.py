import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from post_on_telegram.credentials import resolve_credentials
from post_on_telegram.errors import ConfigError


class TestCredentials(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.credentials_file = Path(self.temp_dir.name) / "credentials.json"
        self.original_env = os.environ.copy()

    def tearDown(self):
        self.temp_dir.cleanup()
        for key in ["POST_ON_TELEGRAM_TOKEN", "POST_ON_TELEGRAM_CHAT_ID"]:
            if key in os.environ:
                del os.environ[key]
        os.environ.update(self.original_env)

    def _write_creds(self, data, encoding="utf-8-sig"):
        self.credentials_file.write_text(json.dumps(data), encoding=encoding)

    def test_explicit_args(self):
        creds = resolve_credentials(token="123456:test_token", chat_id="test_chat")
        self.assertEqual(creds["bot_token"], "123456:test_token")
        self.assertEqual(creds["chat_id"], "test_chat")

    def test_env_vars(self):
        os.environ["POST_ON_TELEGRAM_TOKEN"] = "123456:env_token"
        os.environ["POST_ON_TELEGRAM_CHAT_ID"] = "env_chat"
        creds = resolve_credentials()
        self.assertEqual(creds["bot_token"], "123456:env_token")
        self.assertEqual(creds["chat_id"], "env_chat")

    def test_file_valid(self):
        self._write_creds({"bot_token": "123456:file_token", "chat_id": "file_chat"})
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds["bot_token"], "123456:file_token")
        self.assertEqual(creds["chat_id"], "file_chat")

    def test_file_legacy_aliases(self):
        self._write_creds({"telegram_token": "123456:legacy_token", "telegram_id": "legacy_chat"})
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds["bot_token"], "123456:legacy_token")
        self.assertEqual(creds["chat_id"], "legacy_chat")

    def test_file_missing_file_strict(self):
        with self.assertRaises(ConfigError):
            resolve_credentials(credentials_file="nonexistent_creds_file.json", strict=True)

    def test_file_missing_file_non_strict(self):
        creds = resolve_credentials(credentials_file="nonexistent_creds_file.json", strict=False)
        self.assertEqual(creds["bot_token"], "")
        self.assertEqual(creds["chat_id"], "")

    def test_file_empty_strict(self):
        self.credentials_file.write_text("", encoding="utf-8-sig")
        with self.assertRaises(ConfigError):
            resolve_credentials(credentials_file=str(self.credentials_file), strict=True)

    def test_file_empty_non_strict(self):
        self.credentials_file.write_text("", encoding="utf-8-sig")
        creds = resolve_credentials(credentials_file=str(self.credentials_file), strict=False)
        self.assertEqual(creds["bot_token"], "")

    def test_file_invalid_json(self):
        self.credentials_file.write_text("{bad json", encoding="utf-8-sig")
        with self.assertRaises(ConfigError):
            resolve_credentials(credentials_file=str(self.credentials_file), strict=True)
        creds = resolve_credentials(credentials_file=str(self.credentials_file), strict=False)
        self.assertEqual(creds["bot_token"], "")

    def test_file_json_list(self):
        self.credentials_file.write_text("['token', 'chat']", encoding="utf-8-sig")
        with self.assertRaises(ConfigError):
            resolve_credentials(credentials_file=str(self.credentials_file), strict=True)
        creds = resolve_credentials(credentials_file=str(self.credentials_file), strict=False)
        self.assertEqual(creds["bot_token"], "")

    def test_file_missing_keys(self):
        self._write_creds({"other_key": "val"})
        with self.assertRaises(ConfigError):
            resolve_credentials(credentials_file=str(self.credentials_file), strict=True)

    def test_int_chat_id(self):
        self._write_creds({"bot_token": "123456:token", "chat_id": -1001234567890})
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds["chat_id"], "-1001234567890")

    def test_whitespace_and_bom(self):
        # Writing with encoding="utf-8" and \ufeff creates actual UTF-8 BOM bytes on disk
        self.credentials_file.write_bytes(
            '\ufeff{"bot_token": "  123456:token ", "chat_id": " -100123 "}'.encode("utf-8")
        )
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds["bot_token"], "123456:token")
        self.assertEqual(creds["chat_id"], "-100123")

    def test_token_without_colon_strict(self):
        with self.assertRaises(ConfigError):
            resolve_credentials(token="invalidtokenwithoutcolon", chat_id="123", strict=True)

    def test_token_without_colon_non_strict(self):
        creds = resolve_credentials(token="invalidtokenwithoutcolon", chat_id="123", strict=False)
        self.assertEqual(creds["bot_token"], "invalidtokenwithoutcolon")

    def test_precedence_explicit_over_file_and_env(self):
        self._write_creds({"bot_token": "1:file_token", "chat_id": "file_chat"})
        os.environ["POST_ON_TELEGRAM_TOKEN"] = "1:env_token"
        os.environ["POST_ON_TELEGRAM_CHAT_ID"] = "env_chat"

        creds = resolve_credentials(
            token="1:explicit_token",
            chat_id="explicit_chat",
            credentials_file=str(self.credentials_file),
        )
        self.assertEqual(creds["bot_token"], "1:explicit_token")
        self.assertEqual(creds["chat_id"], "explicit_chat")

    def test_precedence_file_over_env(self):
        self._write_creds({"bot_token": "1:file_token", "chat_id": "file_chat"})
        os.environ["POST_ON_TELEGRAM_TOKEN"] = "1:env_token"
        os.environ["POST_ON_TELEGRAM_CHAT_ID"] = "env_chat"

        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds["bot_token"], "1:file_token")
        self.assertEqual(creds["chat_id"], "file_chat")

    def test_credentials_json_not_dict_strict(self):
        self.credentials_file.write_text('"a string"', encoding="utf-8")
        with self.assertRaises(ConfigError):
            resolve_credentials(credentials_file=str(self.credentials_file), strict=True)
        creds = resolve_credentials(credentials_file=str(self.credentials_file), strict=False)
        self.assertEqual(creds["bot_token"], "")
        from post_on_telegram.credentials import _check_file_permissions

        with patch("post_on_telegram.credentials.os.name", "posix"):
            with patch("post_on_telegram.credentials.os.stat") as mock_stat:
                mock_stat.return_value.st_mode = 0o666  # group/other readable
                with self.assertLogs("post_on_telegram", level="WARNING") as cm:
                    _check_file_permissions(self.credentials_file)
                self.assertTrue(any("chmod 600" in log for log in cm.output))

    def test_empty_string_chat_id_in_file(self):
        self._write_creds({"bot_token": "123456:token", "chat_id": ""})
        with self.assertRaises(ConfigError):
            resolve_credentials(credentials_file=str(self.credentials_file), strict=True)
        creds = resolve_credentials(credentials_file=str(self.credentials_file), strict=False)
        self.assertEqual(creds["chat_id"], "")

    def test_credentials_path_is_directory(self):
        dir_path = Path(self.temp_dir.name) / "some_dir"
        dir_path.mkdir()
        with self.assertRaises(ConfigError):
            resolve_credentials(credentials_file=str(dir_path), strict=True)
        creds = resolve_credentials(credentials_file=str(dir_path), strict=False)
        self.assertEqual(creds["bot_token"], "")

    def test_utf16_le_credentials_file(self):
        """UTF-16 LE credentials file (BOM FF FE) loads correctly."""
        data = '{"bot_token": "123456:utf16_token", "chat_id": "utf16_chat"}'
        self.credentials_file.write_bytes(b"\xff\xfe" + data.encode("utf-16-le"))
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds["bot_token"], "123456:utf16_token")
        self.assertEqual(creds["chat_id"], "utf16_chat")

    def test_utf16_be_credentials_file(self):
        """UTF-16 BE credentials file (BOM FE FF) loads correctly."""
        data = '{"bot_token": "123456:utf16be_token", "chat_id": "utf16be_chat"}'
        self.credentials_file.write_bytes(b"\xfe\xff" + data.encode("utf-16-be"))
        creds = resolve_credentials(credentials_file=str(self.credentials_file))
        self.assertEqual(creds["bot_token"], "123456:utf16be_token")
        self.assertEqual(creds["chat_id"], "utf16be_chat")

    def test_binary_garbage_non_strict(self):
        """Binary garbage file with strict=False gives enabled=False and no exception."""
        self.credentials_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe\x00\x00")
        creds = resolve_credentials(credentials_file=str(self.credentials_file), strict=False)
        self.assertEqual(creds["bot_token"], "")
        self.assertEqual(creds["chat_id"], "")

    def test_binary_garbage_strict(self):
        """Binary garbage file with strict=True raises ConfigError."""
        self.credentials_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe\x00\x00")
        with self.assertRaises(ConfigError):
            resolve_credentials(credentials_file=str(self.credentials_file), strict=True)

    def test_path_exists_permission_error_non_strict(self):
        """Path whose stat raises PermissionError does not crash in non-strict mode."""
        with patch.object(Path, "exists", side_effect=PermissionError("Access denied")):
            creds = resolve_credentials(credentials_file="some_path", strict=False)
            self.assertEqual(creds["bot_token"], "")
            self.assertEqual(creds["chat_id"], "")

    def test_path_exists_permission_error_strict(self):
        """Path whose stat raises PermissionError raises ConfigError in strict mode."""
        with patch.object(Path, "exists", side_effect=PermissionError("Access denied")):
            with self.assertRaises(ConfigError):
                resolve_credentials(credentials_file="some_path", strict=True)

    def test_file_token_only_env_chat_id_strict(self):
        """strict=True, file with token only, chat id from env var succeeds."""
        self._write_creds({"bot_token": "123456:file_token"})
        os.environ["POST_ON_TELEGRAM_CHAT_ID"] = "env_chat_id"
        creds = resolve_credentials(credentials_file=str(self.credentials_file), strict=True)
        self.assertEqual(creds["bot_token"], "123456:file_token")
        self.assertEqual(creds["chat_id"], "env_chat_id")

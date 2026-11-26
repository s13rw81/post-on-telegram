import json
import os
import tempfile
import unittest

import responses

from post_on_telegram import Poster, escape_markdown_v2, format_pre

CANARY = "123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq"
CHAT_ID = "-1001234567890"


class TestReadmeExamples(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.creds_file = os.path.join(self.temp_dir.name, "credentials.json")
        with open(self.creds_file, "w", encoding="utf-8") as f:
            json.dump({"bot_token": CANARY, "chat_id": CHAT_ID}, f)
        self.orig_env = os.environ.copy()

    def tearDown(self):
        self.temp_dir.cleanup()
        for k in ["POST_ON_TELEGRAM_TOKEN", "POST_ON_TELEGRAM_CHAT_ID"]:
            os.environ.pop(k, None)
        os.environ.update(self.orig_env)

    @responses.activate
    def test_quickstart_basic_send(self):
        """README: Quick start -> Basic send"""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(responses.POST, url, json={"ok": True, "result": {}}, status=200)

        poster = Poster(token=CANARY, chat_id=CHAT_ID)
        ok = poster.send("Hello, world!")
        self.assertTrue(ok)

    @responses.activate
    def test_quickstart_env_vars(self):
        """README: Quick start -> Using env vars"""
        os.environ["POST_ON_TELEGRAM_TOKEN"] = CANARY
        os.environ["POST_ON_TELEGRAM_CHAT_ID"] = CHAT_ID

        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(responses.POST, url, json={"ok": True, "result": {}}, status=200)

        poster = Poster()
        ok = poster.send("Hello from env vars!")
        self.assertTrue(ok)

    @responses.activate
    def test_quickstart_explicit_credentials(self):
        """README: Quick start -> Explicit token/chat_id"""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(responses.POST, url, json={"ok": True, "result": {}}, status=200)

        poster = Poster(token=CANARY, chat_id=CHAT_ID)
        ok = poster.send("Hello with explicit credentials!")
        self.assertTrue(ok)

    @responses.activate
    def test_quickstart_check_boolean_and_last_error(self):
        """README: Quick start -> Check boolean result and last error"""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST, url, json={"ok": False, "description": "Unauthorized"}, status=401
        )

        poster = Poster(token=CANARY, chat_id=CHAT_ID)
        if poster.send("Hello!"):
            result = "Sent!"
        else:
            result = f"Failed: {poster.last_error}"
        self.assertIn("Failed:", result)

    @responses.activate
    def test_formatting_examples(self):
        """README: Formatting -> plain, HTML, MarkdownV2, format_pre"""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(responses.POST, url, json={"ok": True, "result": {}}, status=200)

        poster = Poster(token=CANARY, chat_id=CHAT_ID)
        self.assertTrue(poster.send("Hello!"))
        self.assertTrue(poster.send("Hello <b>world</b>!", parse_mode="HTML"))
        self.assertTrue(
            poster.send(escape_markdown_v2("**Hello** world!"), parse_mode="MarkdownV2")
        )

        table = format_pre("a | b\n--- | ---\n1 | 2")
        self.assertTrue(poster.send(table, parse_mode="HTML"))

    @responses.activate
    def test_send_document_example(self):
        """README: Sending files"""
        url = f"https://api.telegram.org/bot{CANARY}/sendDocument"
        responses.add(responses.POST, url, json={"ok": True, "result": {}}, status=200)

        doc_path = os.path.join(self.temp_dir.name, "file.pdf")
        with open(doc_path, "wb") as f:
            f.write(b"%PDF-1.4 mock")

        poster = Poster(token=CANARY, chat_id=CHAT_ID)
        ok = poster.send_document(doc_path, caption="Report")
        self.assertTrue(ok)

    def test_readme_cli_flags_exist_in_argparse(self):
        """Verify all CLI flags shown in README exist in the argparse parser."""
        from post_on_telegram.cli import _build_parser

        parser = _build_parser()
        options = parser._option_string_actions.keys()

        expected_flags = [
            "--credentials",
            "--parse-mode",
            "--no-preview",
            "--silent",
            "--chat-id",
            "--file",
            "--caption",
            "--check",
            "--version",
        ]
        for flag in expected_flags:
            self.assertIn(flag, options)

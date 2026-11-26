import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import responses

from post_on_telegram.cli import main

CANARY = "123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq"
CHAT_ID = "-1001234567890"


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.creds_file = os.path.join(self.temp_dir.name, "credentials.json")
        with open(self.creds_file, "w", encoding="utf-8") as f:
            json.dump({"bot_token": CANARY, "chat_id": CHAT_ID}, f)
        self.orig_env = os.environ.copy()
        for k in ["POST_ON_TELEGRAM_TOKEN", "POST_ON_TELEGRAM_CHAT_ID"]:
            os.environ.pop(k, None)

    def tearDown(self):
        self.temp_dir.cleanup()
        for k in ["POST_ON_TELEGRAM_TOKEN", "POST_ON_TELEGRAM_CHAT_ID"]:
            os.environ.pop(k, None)
        os.environ.update(self.orig_env)

    def test_version_flag(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("post-on-telegram", stdout.getvalue())

    def test_token_arg_rejected_with_code_2(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(["--token", CANARY, "Hello"])
        self.assertEqual(code, 2)
        err = stderr.getvalue()
        self.assertIn("not supported for security reasons", err)
        self.assertNotIn(CANARY, err)
        self.assertNotIn(CANARY, stdout.getvalue())

    def test_check_no_credentials_exit_code_2(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(["--check"])
        self.assertEqual(code, 2)
        self.assertIn("Check failed", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    @responses.activate
    def test_check_success_prints_username(self):
        url = f"https://api.telegram.org/bot{CANARY}/getMe"
        responses.add(
            responses.GET,
            url,
            json={"ok": True, "result": {"username": "test_bot"}},
            status=200,
        )

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(["--credentials", self.creds_file, "--check"])
        self.assertEqual(code, 0)
        self.assertIn("@test_bot", stdout.getvalue())
        self.assertNotIn(CANARY, stdout.getvalue())
        self.assertNotIn(CANARY, stderr.getvalue())

    @responses.activate
    def test_check_failure_exit_code_1(self):
        url = f"https://api.telegram.org/bot{CANARY}/getMe"
        responses.add(
            responses.GET, url, json={"ok": False, "description": "Unauthorized"}, status=401
        )

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(["--credentials", self.creds_file, "--check"])
        self.assertEqual(code, 1)
        self.assertIn("Check failed", stderr.getvalue())
        self.assertNotIn(CANARY, stderr.getvalue())

    @responses.activate
    def test_send_message_argv_success(self):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(responses.POST, url, json={"ok": True, "result": {}}, status=200)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(["--credentials", self.creds_file, "Hello from CLI"])
        self.assertEqual(code, 0)
        self.assertEqual(len(responses.calls), 1)
        self.assertNotIn(CANARY, stdout.getvalue())
        self.assertNotIn(CANARY, stderr.getvalue())

    @responses.activate
    def test_send_message_stdin(self):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(responses.POST, url, json={"ok": True, "result": {}}, status=200)

        stdin = io.StringIO("Message from piped stdin")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdin", stdin), patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(["--credentials", self.creds_file, "-"])
        self.assertEqual(code, 0)
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_credentials_via_env_vars(self):
        os.environ["POST_ON_TELEGRAM_TOKEN"] = CANARY
        os.environ["POST_ON_TELEGRAM_CHAT_ID"] = CHAT_ID

        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(responses.POST, url, json={"ok": True, "result": {}}, status=200)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(["Env var message"])
        self.assertEqual(code, 0)

    @responses.activate
    def test_cli_flags_mapping(self):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(responses.POST, url, json={"ok": True, "result": {}}, status=200)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(
                [
                    "--credentials",
                    self.creds_file,
                    "--parse-mode",
                    "html",
                    "--no-preview",
                    "--silent",
                    "--chat-id",
                    "-100888888",
                    "<b>Hello</b>",
                ]
            )
        self.assertEqual(code, 0)
        req_body = json.loads(responses.calls[0].request.body.decode("utf-8"))
        self.assertEqual(req_body["parse_mode"], "HTML")
        self.assertTrue(req_body["disable_web_page_preview"])
        self.assertTrue(req_body["disable_notification"])
        self.assertEqual(req_body["chat_id"], "-100888888")

    @responses.activate
    def test_send_document_cli(self):
        url = f"https://api.telegram.org/bot{CANARY}/sendDocument"
        responses.add(responses.POST, url, json={"ok": True, "result": {}}, status=200)

        doc_path = os.path.join(self.temp_dir.name, "cli_doc.txt")
        with open(doc_path, "w") as f:
            f.write("Document text")

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(
                [
                    "--credentials",
                    self.creds_file,
                    "--file",
                    doc_path,
                    "--caption",
                    "CLI Caption",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(len(responses.calls), 1)

    def test_cli_missing_message_exits_2(self):
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            code = main(["--credentials", self.creds_file])
        self.assertEqual(code, 2)
        self.assertIn("MESSAGE or --file or --check required", stderr.getvalue())

    def test_cli_unconfigured_message_exits_2(self):
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            code = main(["Hello without credentials"])
        self.assertEqual(code, 2)
        self.assertIn("Configuration error", stderr.getvalue())

    @responses.activate
    @responses.activate
    def test_cli_send_message_failure_stderr(self):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST, url, json={"ok": False, "description": "Blocked by user"}, status=403
        )
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            code = main(["--credentials", self.creds_file, "Blocked message"])
        self.assertEqual(code, 1)
        self.assertIn("Blocked by user", stderr.getvalue())
        url = f"https://api.telegram.org/bot{CANARY}/sendDocument"
        responses.add(
            responses.POST, url, json={"ok": False, "description": "Upload failed"}, status=400
        )
        doc = os.path.join(self.temp_dir.name, "doc.txt")
        with open(doc, "w") as f:
            f.write("text")

        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            code = main(["--credentials", self.creds_file, "--file", doc])
        self.assertEqual(code, 1)
        self.assertIn("Upload failed", stderr.getvalue())

import subprocess
import sys
import tempfile
import os

from post_on_telegram.cli import main


class TestCLI(unittest.TestCase):
    def test_version(self):
        result = subprocess.run(
            [sys.executable, "-m", "post_on_telegram", "--version"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("post-on-telegram", result.stdout)

    def test_check_no_creds(self):
        result = subprocess.run(
            [sys.executable, "-m", "post_on_telegram", "--check"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("No credentials", result.stderr)

    def test_check_with_creds(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"bot_token": "123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq",
                       "chat_id": "-1001234567890"}, f)
            fname = f.name
        try:
            result = subprocess.run(
                [sys.executable, "-m", "post_on_telegram", "--check", "--credentials", fname],
                capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("testbot", result.stdout)
        finally:
            os.unlink(fname)

    def test_send_stdin(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"bot_token": "123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq",
                       "chat_id": "-1001234567890"}, f)
            fname = f.name
        try:
            result = subprocess.run(
                [sys.executable, "-m", "post_on_telegram", "--credentials", fname, "--stdin"],
                input="Hello from stdin\n",
                capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0)
        finally:
            os.unlink(fname)

    def test_send_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"bot_token": "123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq",
                       "chat_id": "-1001234567890"}, f)
            fname = f.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("File content")
            file_fname = f.name
        try:
            result = subprocess.run(
                [sys.executable, "-m", "post_on_telegram", "--credentials", fname, "--file", file_fname],
                capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0)
        finally:
            os.unlink(fname)
            os.unlink(file_fname)

    def test_no_token_argument(self):
        result = subprocess.run(
            [sys.executable, "-m", "post_on_telegram", "--token", "123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("not accept token", result.stderr)

    def test_parse_mode_html(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"bot_token": "123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq",
                       "chat_id": "-1001234567890"}, f)
            fname = f.name
        try:
            result = subprocess.run(
                [sys.executable, "-m", "post_on_telegram", "--credentials", fname, "--parse-mode", "html", "Hello"],
                capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0)
        finally:
            os.unlink(fname)

    def test_parse_mode_markdownv2(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"bot_token": "123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq",
                       "chat_id": "-1001234567890"}, f)
            fname = f.name
        try:
            result = subprocess.run(
                [sys.executable, "-m", "post_on_telegram", "--credentials", fname, "--parse-mode", "markdownv2", "Hello"],
                capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0)
        finally:
            os.unlink(fname)

    def test_exit_codes(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"bot_token": "123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq",
                       "chat_id": "-1001234567890"}, f)
            fname = f.name
        try:
            # Success
            result = subprocess.run(
                [sys.executable, "-m", "post_on_telegram", "--credentials", fname, "Hello"],
                capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0)
        finally:
            os.unlink(fname)
</write_to_file>
</tool_call>
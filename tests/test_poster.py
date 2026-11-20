import unittest
from unittest.mock import Mock, patch
from post_on_telegram.poster import Poster
from post_on_telegram.errors import ConfigError, PostOnTelegramError


class TestPoster(unittest.TestCase):
    def setUp(self):
        self.poster = Poster()

    def test_initialization_with_explicit_creds(self):
        self.poster = Poster(token="test_token", chat_id="test_chat")
        self.assertEqual(self.poster._token, "test_token")
        self.assertEqual(self.poster._chat_id, "test_chat")
        self.assertTrue(self.poster.enabled)

    def test_initialization_with_credentials_file(self):
        self.poster = Poster(credentials_file="dummy.json")
        self.assertTrue(self.poster.enabled)

    def test_initialization_with_env_vars(self):
        self.poster = Poster()
        self.poster._token = "env_token:123456"
        self.poster._chat_id = "env_chat"
        self.assertTrue(self.poster.enabled)

    def test_initialization_strict_failure(self):
        self.poster = Poster(strict=True)
        with self.assertRaises(ConfigError):
            self.poster = Poster(token="invalid", chat_id="invalid")

    def test_initialization_non_strict_warning(self):
        self.poster = Poster(strict=False)
        self.assertFalse(self.poster.enabled)

    def test_send_success(self):
        with patch('post_on_telegram.poster.Poster._send_with_retries') as mock_send:
            mock_send.return_value = Mock(status_code=200, json=lambda: {"ok": True})
            result = self.poster.send("test message")
            self.assertTrue(result)
            self.assertIsNone(self.poster.last_error)

    def test_send_failure(self):
        with patch('post_on_telegram.poster.Poster._send_with_retries') as mock_send:
            mock_send.side_effect = PostOnTelegramError("test error")
            result = self.poster.send("test message")
            self.assertFalse(result)
            self.assertIsNotNone(self.poster.last_error)

    def test_send_parse_error_fallback(self):
        with patch('post_on_telegram.poster.Poster._send_with_retries') as mock_send:
            mock_send.side_effect = PostOnTelegramError("can't parse entities")
            result = self.poster.send("test message", parse_mode="HTML")
            self.assertFalse(result)

    def test_send_invalid_parse_mode(self):
        result = self.poster.send("test message", parse_mode="invalid")
        self.assertFalse(result)
        self.assertEqual(self.poster.last_error, "invalid parse_mode: 'invalid'")

    def test_send_empty_message(self):
        result = self.poster.send("")
        self.assertFalse(result)
        self.assertEqual(self.poster.last_error, "empty message")

    def test_send_none_message(self):
        result = self.poster.send(None)
        self.assertFalse(result)
        self.assertEqual(self.poster.last_error, "empty message")

    def test_send_non_string(self):
        result = self.poster.send(123)
        self.assertTrue(result)

    def test_send_chat_id_override(self):
        with patch('post_on_telegram.poster.Poster._send_with_retries') as mock_send:
            mock_send.return_value = Mock(status_code=200, json=lambda: {"ok": True})
            result = self.poster.send("test message", chat_id="override_chat")
            self.assertTrue(result)

    def test_send_parse_mode_html(self):
        with patch('post_on_telegram.poster.Poster._send_with_retries') as mock_send:
            mock_send.return_value = Mock(status_code=200, json=lambda: {"ok": True})
            result = self.poster.send("test message", parse_mode="HTML")
            self.assertTrue(result)

    def test_send_parse_mode_markdownv2(self):
        with patch('post_on_telegram.poster.Poster._send_with_retries') as mock_send:
            mock_send.return_value = Mock(status_code=200, json=lambda: {"ok": True})
            result = self.poster.send("test message", parse_mode="MarkdownV2")
            self.assertTrue(result)

    def test_send_parse_mode_invalid(self):
        result = self.poster.send("test message", parse_mode="invalid")
        self.assertFalse(result)
        self.assertEqual(self.poster.last_error, "invalid parse_mode: 'invalid'")

    def test_send_parse_mode_none(self):
        with patch('post_on_telegram.poster.Poster._send_with_retries') as mock_send:
            mock_send.return_value = Mock(status_code=200, json=lambda: {"ok": True})
            result = self.poster.send("test message", parse_mode=None)
            self.assertTrue(result)

    def test_send_document_success(self):
        with patch('post_on_telegram.poster.Poster._send_with_retries') as mock_send:
            mock_send.return_value = Mock(status_code=200, json=lambda: {"ok": True})
            result = self.poster.send_document("test.txt")
            self.assertTrue(result)

    def test_send_document_missing_file(self):
        result = self.poster.send_document("nonexistent.txt")
        self.assertFalse(result)

    def test_send_document_directory(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.poster.send_document(tmpdir)
            self.assertFalse(result)

    def test_send_document_empty_file(self):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"")
            fname = f.name
        result = self.poster.send_document(fname)
        self.assertFalse(result)

    def test_send_document_large_file(self):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"x" * (51 * 1024 * 1024))
            fname = f.name
        result = self.poster.send_document(fname)
        self.assertFalse(result)

    def test_send_document_caption_truncation(self):
        with patch('post_on_telegram.poster.Poster._send_with_retries') as mock_send:
            mock_send.return_value = Mock(status_code=200, json=lambda: {"ok": True})
            caption = "x" * 2000
            result = self.poster.send_document("test.txt", caption=caption)
            self.assertTrue(result)

    def test_check_success(self):
        with patch('post_on_telegram.poster.Poster._send_with_retries') as mock_send:
            mock_send.return_value = Mock(status_code=200, json=lambda: {"ok": True, "result": {"username": "testbot"}})
            result = self.poster.check()
            self.assertTrue(result)

    def test_check_failure(self):
        with patch('post_on_telegram.poster.Poster._send_with_retries') as mock_send:
            mock_send.side_effect = PostOnTelegramError("test error")
            result = self.poster.check()
            self.assertFalse(result)

    def test_repr_no_token(self):
        self.poster = Poster(token="123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq", chat_id="test_chat")
        repr_str = repr(self.poster)
        self.assertNotIn("AAFakeTokenForTestsOnly", repr_str)
        self.assertIn("123", repr_str)

    def test_str_no_token(self):
        self.poster = Poster(token="123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq", chat_id="test_chat")
        str_str = str(self.poster)
        self.assertNotIn("AAFakeTokenForTestsOnly", str_str)

    def test_last_error_redacted(self):
        with patch('post_on_telegram.poster.Poster._send_with_retries') as mock_send:
            mock_send.side_effect = PostOnTelegramError("https://api.telegram.org/bot123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq/sendMessage")
            self.poster.send("test")
            self.assertNotIn("AAFakeTokenForTestsOnly", self.poster.last_error)

    def test_thread_safety(self):
        import threading
        import time
        results = []
        def send_long():
            with patch('post_on_telegram.poster.Poster._send_with_retries') as mock_send:
                mock_send.return_value = Mock(status_code=200, json=lambda: {"ok": True})
                result = self.poster.send("x" * 5000)
                results.append(result)
        threads = [threading.Thread(target=send_long) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertTrue(all(results))
</write_to_file>
</tool_call>
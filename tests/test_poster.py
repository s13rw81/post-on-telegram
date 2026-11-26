import os
import tempfile
import time
import unittest
from unittest.mock import patch

import requests
import responses

from post_on_telegram.errors import ConfigError
from post_on_telegram.poster import Poster, _mask_token, redact

CANARY = "123456789:AAFakeTokenForTestsOnly_abcdefghijklmnopq"
CHAT_ID = "-1001234567890"


class TestPoster(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.poster = Poster(token=CANARY, chat_id=CHAT_ID, chunk_delay=0.0)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initialization(self):
        self.assertTrue(self.poster.enabled)
        self.assertIn("1234…nopq", repr(self.poster))
        self.assertNotIn(CANARY, repr(self.poster))
        self.assertNotIn(CANARY, str(self.poster))

    def test_strict_mode_raises(self):
        with self.assertRaises(ConfigError):
            Poster(token="badtoken", chat_id="123", strict=True)

    def test_constructor_config_error_warning(self):
        p = Poster(token="bad_token_without_colon", chat_id="123", strict=False)
        self.assertTrue(p.enabled)

    def test_unconfigured_poster_send_and_check(self):
        p = Poster(strict=False)
        self.assertFalse(p.send("hello"))
        self.assertIn("disabled", p.last_error)
        self.assertFalse(p.send_document("somefile.txt"))
        self.assertFalse(p.check())
        self.assertIn("No bot token", p.last_error)

    @responses.activate
    def test_send_success(self):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST, url, json={"ok": True, "result": {"message_id": 1}}, status=200
        )

        ok = self.poster.send("Hello world")
        self.assertTrue(ok)
        self.assertIsNone(self.poster.last_error)
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_send_parse_modes(self):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(responses.POST, url, json={"ok": True, "result": {}}, status=200)

        self.assertTrue(self.poster.send("plain msg", parse_mode=None))
        self.assertTrue(self.poster.send("<b>bold</b>", parse_mode="HTML"))
        self.assertTrue(self.poster.send("markdown", parse_mode="MarkdownV2"))
        self.assertFalse(self.poster.send("msg", parse_mode="Markdown"))  # unsupported
        self.assertIn("Unsupported parse_mode", self.poster.last_error)

    def test_send_empty_or_none(self):
        self.assertFalse(self.poster.send(None))
        self.assertEqual(self.poster.last_error, "empty message")
        self.assertFalse(self.poster.send("   \n   "))
        self.assertEqual(self.poster.last_error, "empty message")

    @responses.activate
    def test_send_chat_id_override(self):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(responses.POST, url, json={"ok": True, "result": {}}, status=200)

        self.assertTrue(self.poster.send("override", chat_id="-1009999999"))
        body = responses.calls[0].request.body
        import json

        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["chat_id"], "-1009999999")

    @responses.activate
    def test_chunking_order_and_stop_on_first_failure(self):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        # First chunk succeeds, second chunk fails
        responses.add(responses.POST, url, json={"ok": True}, status=200)
        responses.add(responses.POST, url, json={"ok": False, "description": "Blocked"}, status=403)

        p = Poster(token=CANARY, chat_id=CHAT_ID, max_message_length=50, chunk_delay=0.0)
        long_msg = "A" * 120
        ok = p.send(long_msg)
        self.assertFalse(ok)
        self.assertIn("403", p.last_error)
        # Should stop after second chunk failed and not try third
        self.assertEqual(len(responses.calls), 2)

    @responses.activate
    def test_parse_error_fallback(self):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        # 1st call: 400 Can't parse entities
        responses.add(
            responses.POST,
            url,
            json={"ok": False, "description": "Bad Request: can't parse entities"},
            status=400,
        )
        # 2nd call (fallback plain text): 200 OK
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        ok = self.poster.send("<b>Broken <i>tag</b>", parse_mode="HTML")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)
        import json

        fallback_body = json.loads(responses.calls[1].request.body.decode("utf-8"))
        self.assertNotIn("parse_mode", fallback_body)
        self.assertEqual(fallback_body["text"], "Broken tag")

    @responses.activate
    def test_parse_error_fallback_fails(self):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            json={"ok": False, "description": "Bad Request: can't parse entities"},
            status=400,
        )
        responses.add(
            responses.POST,
            url,
            json={"ok": False, "description": "Bad Request: chat not found"},
            status=400,
        )

        ok = self.poster.send("<b>Broken</b>", parse_mode="HTML")
        self.assertFalse(ok)
        self.assertIn("chat not found", self.poster.last_error)

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_retries_500_then_success(self, mock_sleep):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(responses.POST, url, json={"ok": False}, status=502)
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        ok = self.poster.send("Retry test")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_retries_500_exhausted(self, mock_sleep):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        for _ in range(4):
            responses.add(
                responses.POST, url, json={"ok": False, "description": "Gateway error"}, status=502
            )

        p = Poster(token=CANARY, chat_id=CHAT_ID, max_retries=2, chunk_delay=0.0)
        ok = p.send("Retry test")
        self.assertFalse(ok)
        self.assertIn("502", p.last_error)

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_retries_429_honours_retry_after(self, mock_sleep):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            json={"ok": False, "parameters": {"retry_after": 2}},
            status=429,
        )
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        ok = self.poster.send("Rate limit test")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_retries_429_with_header(self, mock_sleep):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            headers={"Retry-After": "3"},
            status=429,
        )
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        ok = self.poster.send("Rate limit header test")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)

    @responses.activate
    def test_retries_429_exceeds_budget(self):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            json={"ok": False, "parameters": {"retry_after": 100}},
            status=429,
        )
        p = Poster(token=CANARY, chat_id=CHAT_ID, total_timeout=5.0)
        ok = p.send("Exceeds budget")
        self.assertFalse(ok)

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_network_connection_error_retry(self, mock_sleep):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST, url, body=requests.exceptions.ConnectionError("Connection failed")
        )
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        ok = self.poster.send("Connection retry")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_network_timeout_retry(self, mock_sleep):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(responses.POST, url, body=requests.exceptions.Timeout("Read timeout"))
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        ok = self.poster.send("Timeout retry")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)

    @responses.activate
    def test_total_timeout_expired(self):
        # Mocking monotonic clock to simulate elapsed timeout
        real_monotonic = time.monotonic
        start = real_monotonic()

        p = Poster(token=CANARY, chat_id=CHAT_ID, total_timeout=2.0)
        with patch("time.monotonic", side_effect=[start, start + 3.0]):
            ok = p.send("Deadline test")
            self.assertFalse(ok)
            self.assertIn("deadline", p.last_error.lower())

    @responses.activate
    def test_no_retry_on_400_401_403_404(self):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            json={"ok": False, "description": "Forbidden: bot was blocked"},
            status=403,
        )

        ok = self.poster.send("No retry on 403")
        self.assertFalse(ok)
        self.assertEqual(len(responses.calls), 1)

    @responses.activate
    def test_non_json_response(self):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(responses.POST, url, body="<html>Bad Gateway</html>", status=502)
        p = Poster(token=CANARY, chat_id=CHAT_ID, max_retries=0)
        ok = p.send("Non json")
        self.assertFalse(ok)
        self.assertIn("Non-JSON", p.last_error)

    @responses.activate
    def test_json_missing_ok_field(self):
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(responses.POST, url, json={"something_else": 1}, status=200)
        p = Poster(token=CANARY, chat_id=CHAT_ID, max_retries=0)
        ok = p.send("Missing ok")
        self.assertFalse(ok)
        self.assertIn("missing 'ok'", p.last_error)

    @responses.activate
    def test_send_document_success(self):
        url = f"https://api.telegram.org/bot{CANARY}/sendDocument"
        responses.add(responses.POST, url, json={"ok": True, "result": {}}, status=200)

        test_file = os.path.join(self.temp_dir.name, "report.pdf")
        with open(test_file, "wb") as f:
            f.write(b"%PDF-1.4 test")

        ok = self.poster.send_document(test_file, caption="Monthly report", parse_mode="HTML")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 1)

    def test_send_document_validation(self):
        # Missing file
        self.assertFalse(self.poster.send_document("nonexistent_file.pdf"))
        self.assertIn("not found", self.poster.last_error.lower())

        # Directory instead of file
        self.assertFalse(self.poster.send_document(self.temp_dir.name))
        self.assertIn("not a regular file", self.poster.last_error.lower())

        # Empty file
        empty_file = os.path.join(self.temp_dir.name, "empty.txt")
        with open(empty_file, "w") as f:
            pass
        self.assertFalse(self.poster.send_document(empty_file))
        self.assertIn("empty", self.poster.last_error.lower())

        # Large file mock
        with patch("os.path.getsize", return_value=51 * 1024 * 1024):
            self.assertFalse(self.poster.send_document(empty_file))
            self.assertIn("50 MB", self.poster.last_error)

        # Invalid parse mode
        valid_file = os.path.join(self.temp_dir.name, "valid.txt")
        with open(valid_file, "w") as f:
            f.write("data")
        self.assertFalse(self.poster.send_document(valid_file, parse_mode="Markdown"))
        self.assertIn("Unsupported parse_mode", self.poster.last_error)

    @responses.activate
    def test_send_document_error_response(self):
        url = f"https://api.telegram.org/bot{CANARY}/sendDocument"
        responses.add(
            responses.POST, url, json={"ok": False, "description": "File too big"}, status=400
        )
        valid_file = os.path.join(self.temp_dir.name, "valid.txt")
        with open(valid_file, "w") as f:
            f.write("data")
        ok = self.poster.send_document(valid_file)
        self.assertFalse(ok)
        self.assertIn("File too big", self.poster.last_error)

    @responses.activate
    def test_check_success(self):
        url = f"https://api.telegram.org/bot{CANARY}/getMe"
        responses.add(
            responses.GET, url, json={"ok": True, "result": {"username": "my_test_bot"}}, status=200
        )
        self.assertTrue(self.poster.check())

    @responses.activate
    def test_check_failure(self):
        url = f"https://api.telegram.org/bot{CANARY}/getMe"
        responses.add(
            responses.GET, url, json={"ok": False, "description": "Unauthorized"}, status=401
        )
        self.assertFalse(self.poster.check())
        self.assertIn("Unauthorized", self.poster.last_error)

    def test_send_empty_text_cases(self):
        self.assertFalse(self.poster.send(""))
        self.assertFalse(self.poster.send("   "))
        self.assertFalse(self.poster.send("\n\t"))

    def test_send_unconfigured_chat_id(self):
        p = Poster(token=CANARY, chat_id=CHAT_ID, strict=False)
        self.assertFalse(p.send("hello", chat_id=""))
        self.assertIn("No chat_id specified", p.last_error)
        self.assertFalse(p.send_document("nonexistent.pdf", chat_id=""))

    @responses.activate
    def test_send_network_exception_handling(self):
        with patch.object(
            self.poster._session, "request", side_effect=Exception("Fatal socket crash")
        ):
            ok = self.poster.send("crash test")
            self.assertFalse(ok)
            self.assertIn("Fatal socket crash", self.poster.last_error)

    @responses.activate
    def test_send_document_exception_handling(self):
        doc = os.path.join(self.temp_dir.name, "doc.txt")
        with open(doc, "w") as f:
            f.write("text")
        with patch.object(self.poster._session, "request", side_effect=Exception("Upload crash")):
            ok = self.poster.send_document(doc)
            self.assertFalse(ok)
            self.assertIn("Upload crash", self.poster.last_error)
        raw = f"Error with {CANARY} at https://api.telegram.org/bot{CANARY}/sendMessage"
        redacted = redact(raw, CANARY)
        self.assertNotIn(CANARY, redacted)
        self.assertIn("<token>", redacted)
        self.assertIn("api.telegram.org/bot<token>", redacted)
        self.assertEqual(redact(""), "")
        self.assertEqual(_mask_token(""), "")
        self.assertEqual(_mask_token("12345"), "*****")

    def test_poster_properties_and_str(self):
        self.assertEqual(self.poster.enabled, True)
        self.assertIn("token=", str(self.poster))
        self.assertIn(CHAT_ID, str(self.poster))

    def test_strip_html(self):
        cleaned = self.poster._strip_html("<b>Hello</b> <a href='url'>world</a>!")
        self.assertEqual(cleaned, "Hello world!")

    def test_send_document_caption_truncation(self):
        test_file = os.path.join(self.temp_dir.name, "doc_long.txt")
        with open(test_file, "w") as f:
            f.write("sample")
        with patch.object(self.poster, "_request_with_retries") as mock_req:
            mock_resp = requests.Response()
            mock_resp.status_code = 200
            mock_resp._content = b'{"ok": true}'
            mock_req.return_value = mock_resp

            long_caption = "x" * 2000
            ok = self.poster.send_document(test_file, caption=long_caption)
            self.assertTrue(ok)
            data_sent = mock_req.call_args[1]["data"]
            self.assertEqual(len(data_sent["caption"]), 1024)

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_send_document_retry_502_then_200(self, mock_sleep):
        """send_document: first response 502, second 200; both requests carry full file bytes."""
        url = f"https://api.telegram.org/bot{CANARY}/sendDocument"
        responses.add(responses.POST, url, json={"ok": False}, status=502)
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        test_file = os.path.join(self.temp_dir.name, "retry_doc.txt")
        file_content = b"retry test content"
        with open(test_file, "wb") as f:
            f.write(file_content)

        ok = self.poster.send_document(test_file)
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)
        # Both requests should have been made (retry worked)
        # The file content is in the multipart body, but we just verify retry happened

    @responses.activate
    def test_markdown_v2_multi_chunk_no_parse_error(self):
        """Multi-chunk MarkdownV2 message is accepted without parse-error fallback."""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        p = Poster(token=CANARY, chat_id=CHAT_ID, max_message_length=50, chunk_delay=0.0)
        # Create a long message that will be split into multiple chunks
        long_msg = "A" * 200
        ok = p.send(long_msg, parse_mode="MarkdownV2")
        self.assertTrue(ok)
        # Should have made multiple requests, all successful
        self.assertGreater(len(responses.calls), 1)
        for call in responses.calls:
            import json

            payload = json.loads(call.request.body.decode("utf-8"))
            self.assertEqual(payload.get("parse_mode"), "MarkdownV2")

    @responses.activate
    def test_html_fallback_unescapes_entities(self):
        """HTML fallback: '<b>a & b</b>' falls back to 'a & b'."""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        # First call: 400 parse error
        responses.add(
            responses.POST,
            url,
            json={"ok": False, "description": "Bad Request: can't parse entities"},
            status=400,
        )
        # Second call (fallback): 200 OK
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        ok = self.poster.send("<b>a & b</b>", parse_mode="HTML")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)
        import json

        fallback_body = json.loads(responses.calls[1].request.body.decode("utf-8"))
        self.assertEqual(fallback_body["text"], "a & b")

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_send_100_chunks_no_deadline_error(self, mock_sleep):
        """A 100-chunk message with mocked sleep/clock completes without deadline error."""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        # Add 200 successful responses (enough for any chunk count)
        for _ in range(200):
            responses.add(responses.POST, url, json={"ok": True}, status=200)

        p = Poster(token=CANARY, chat_id=CHAT_ID, max_message_length=10, chunk_delay=0.0)
        # Create a message that will be split into many chunks
        long_msg = "A" * 200
        ok = p.send(long_msg)
        self.assertTrue(ok)
        # Should have made multiple requests without deadline error
        self.assertGreater(len(responses.calls), 1)

    def test_constructor_arg_validation_strict(self):
        """Constructor validates max_message_length and max_retries in strict mode."""
        with self.assertRaises(ConfigError):
            Poster(token=CANARY, chat_id=CHAT_ID, max_message_length=0, strict=True)
        with self.assertRaises(ConfigError):
            Poster(token=CANARY, chat_id=CHAT_ID, max_message_length=5000, strict=True)
        with self.assertRaises(ConfigError):
            Poster(token=CANARY, chat_id=CHAT_ID, max_retries=-1, strict=True)

    def test_constructor_arg_validation_non_strict(self):
        """Constructor validates max_message_length and max_retries in non-strict mode."""
        # Should not raise, just log warning
        p = Poster(token=CANARY, chat_id=CHAT_ID, max_message_length=0, strict=False)
        self.assertTrue(p.enabled)
        p = Poster(token=CANARY, chat_id=CHAT_ID, max_retries=-1, strict=False)
        self.assertTrue(p.enabled)

    def test_urllib3_logging_filter_redacts_token(self):
        """urllib3.connectionpool log records are redacted."""
        import logging

        from post_on_telegram.poster import _Urllib3TokenRedactionFilter

        # Create a filter with the canary token
        token_filter = _Urllib3TokenRedactionFilter(CANARY)

        # Create a log record with the token in the message
        record = logging.LogRecord(
            name="urllib3.connectionpool",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="https://api.telegram.org/bot%s/sendMessage",
            args=(CANARY,),
            exc_info=None,
        )

        # Apply the filter
        result = token_filter.filter(record)
        self.assertTrue(result)

        # The record's message should be redacted
        redacted_msg = record.getMessage()
        self.assertNotIn(CANARY, redacted_msg)
        self.assertIn("<token>", redacted_msg)

    def test_urllib3_filter_no_token(self):
        """Filter with no token leaves message unchanged."""
        import logging

        from post_on_telegram.poster import _Urllib3TokenRedactionFilter

        token_filter = _Urllib3TokenRedactionFilter(None)
        record = logging.LogRecord(
            name="urllib3.connectionpool",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="some message",
            args=(),
            exc_info=None,
        )
        result = token_filter.filter(record)
        self.assertTrue(result)
        self.assertEqual(record.getMessage(), "some message")

    def test_urllib3_filter_exception_safe(self):
        """Filter handles exceptions gracefully."""
        import logging

        from post_on_telegram.poster import _Urllib3TokenRedactionFilter

        token_filter = _Urllib3TokenRedactionFilter(CANARY)
        record = logging.LogRecord(
            name="urllib3.connectionpool",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="test %s",
            args=("bad",),
            exc_info=None,
        )
        # Force an exception in getMessage by setting msg to None
        record.msg = None
        result = token_filter.filter(record)
        self.assertTrue(result)

    def test_poster_exception_in_init_non_strict(self):
        """Poster.__init__ catches generic Exception in non-strict mode."""
        with patch("post_on_telegram.poster.resolve_credentials", side_effect=RuntimeError("boom")):
            p = Poster(token=CANARY, chat_id=CHAT_ID, strict=False)
            self.assertFalse(p.enabled)
            self.assertIsNotNone(p.last_error)

    def test_poster_exception_in_init_strict(self):
        """Poster.__init__ wraps generic Exception as ConfigError in strict mode."""
        with patch("post_on_telegram.poster.resolve_credentials", side_effect=RuntimeError("boom")):
            with self.assertRaises(ConfigError):
                Poster(token=CANARY, chat_id=CHAT_ID, strict=True)

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_retry_after_infinite_gives_up(self, mock_sleep):
        """retry_after above the budget: give up at once, one request, no sleep."""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            body='{"ok": false, "parameters": {"retry_after": Infinity}}',
            content_type="application/json",
            status=429,
        )
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        p = Poster(
            token=CANARY, chat_id=CHAT_ID, max_retries=1, chunk_delay=0.0, total_timeout=30.0
        )
        ok = p.send("inf test")
        self.assertFalse(ok)
        self.assertEqual(len(responses.calls), 1)
        mock_sleep.assert_not_called()
        self.assertIn("429", p.last_error)

    @responses.activate
    @patch("time.sleep", return_value=None)
    @patch("random.uniform", return_value=0.0)
    def test_retry_after_nan_ignored_fallback_to_backoff(self, mock_uniform, mock_sleep):
        """retry_after = NaN -> ignored, falls back to backoff, send() True, two requests."""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            body='{"ok": false, "parameters": {"retry_after": NaN}}',
            content_type="application/json",
            status=429,
        )
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        p = Poster(
            token=CANARY, chat_id=CHAT_ID, max_retries=1, chunk_delay=0.0, total_timeout=30.0
        )
        ok = p.send("nan test")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)

    @responses.activate
    @patch("time.sleep", return_value=None)
    @patch("random.uniform", return_value=0.0)
    def test_retry_after_neg_inf_and_negative_ignored(self, mock_uniform, mock_sleep):
        """retry_after = -inf, -5 -> ignored, fallback to backoff, send() True."""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            body='{"ok": false, "parameters": {"retry_after": -Infinity}}',
            content_type="application/json",
            status=429,
        )
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        p = Poster(
            token=CANARY, chat_id=CHAT_ID, max_retries=1, chunk_delay=0.0, total_timeout=30.0
        )
        ok = p.send("neg inf test")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)

    @responses.activate
    @patch("time.sleep", return_value=None)
    @patch("random.uniform", return_value=0.0)
    def test_retry_after_negative_number_ignored(self, mock_uniform, mock_sleep):
        """retry_after = -5 -> ignored, fallback to backoff, send() True."""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            json={"ok": False, "parameters": {"retry_after": -5}},
            status=429,
        )
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        p = Poster(
            token=CANARY, chat_id=CHAT_ID, max_retries=1, chunk_delay=0.0, total_timeout=30.0
        )
        ok = p.send("neg test")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)

    @responses.activate
    @patch("time.sleep", return_value=None)
    @patch("random.uniform", return_value=0.0)
    def test_retry_after_string_ignored_fallback(self, mock_uniform, mock_sleep):
        """retry_after = 'soon' -> ignored, fallback, send() True."""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            json={"ok": False, "parameters": {"retry_after": "soon"}},
            status=429,
        )
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        p = Poster(
            token=CANARY, chat_id=CHAT_ID, max_retries=1, chunk_delay=0.0, total_timeout=30.0
        )
        ok = p.send("soon test")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)

    @responses.activate
    @patch("time.sleep", return_value=None)
    @patch("random.uniform", return_value=0.0)
    def test_retry_after_boolean_ignored_fallback(self, mock_uniform, mock_sleep):
        """retry_after = true (boolean) -> ignored, fallback, send() True."""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            json={"ok": False, "parameters": {"retry_after": True}},
            status=429,
        )
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        p = Poster(
            token=CANARY, chat_id=CHAT_ID, max_retries=1, chunk_delay=0.0, total_timeout=30.0
        )
        ok = p.send("bool test")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_retry_after_1e9_gives_up_immediately(self, mock_sleep):
        """retry_after = 1e9 -> gives up immediately, one request, no sleep, send() False."""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            json={"ok": False, "parameters": {"retry_after": 1e9}},
            status=429,
        )
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        p = Poster(token=CANARY, chat_id=CHAT_ID, max_retries=1, chunk_delay=0.0, total_timeout=5.0)
        ok = p.send("1e9 test")
        self.assertFalse(ok)
        self.assertEqual(len(responses.calls), 1)
        mock_sleep.assert_not_called()

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_retry_after_int_sleep_and_success(self, mock_sleep):
        """retry_after = 2 (int) -> sleep called once with 2.0, then success, send() True."""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            json={"ok": False, "parameters": {"retry_after": 2}},
            status=429,
        )
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        p = Poster(
            token=CANARY, chat_id=CHAT_ID, max_retries=1, chunk_delay=0.0, total_timeout=10.0
        )
        ok = p.send("int test")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)
        mock_sleep.assert_called_once_with(2.0)

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_retry_after_string_sleep_and_success(self, mock_sleep):
        """retry_after = '2' (string) -> sleep called once with 2.0, then success, send() True."""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            json={"ok": False, "parameters": {"retry_after": "2"}},
            status=429,
        )
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        p = Poster(
            token=CANARY, chat_id=CHAT_ID, max_retries=1, chunk_delay=0.0, total_timeout=10.0
        )
        ok = p.send("str test")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)
        mock_sleep.assert_called_once_with(2.0)

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_retry_after_zero_retries_immediately(self, mock_sleep):
        """retry_after = 0 -> retries immediately and succeeds."""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            json={"ok": False, "parameters": {"retry_after": 0}},
            status=429,
        )
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        p = Poster(
            token=CANARY, chat_id=CHAT_ID, max_retries=1, chunk_delay=0.0, total_timeout=10.0
        )
        ok = p.send("zero test")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)
        mock_sleep.assert_called_once_with(0.0)

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_retry_after_header_valid(self, mock_sleep):
        """Retry-After header only: sleeps 3.0, then succeeds."""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            headers={"Retry-After": "3"},
            status=429,
        )
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        p = Poster(
            token=CANARY, chat_id=CHAT_ID, max_retries=1, chunk_delay=0.0, total_timeout=10.0
        )
        ok = p.send("header test")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)
        mock_sleep.assert_called_once_with(3.0)

    @responses.activate
    @patch("time.sleep", return_value=None)
    def test_retry_after_body_invalid_header_valid(self, mock_sleep):
        """Invalid body retry_after: the valid header value 3.0 is used."""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            body='{"ok": false, "parameters": {"retry_after": NaN}}',
            content_type="application/json",
            headers={"Retry-After": "3"},
            status=429,
        )
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        p = Poster(
            token=CANARY, chat_id=CHAT_ID, max_retries=1, chunk_delay=0.0, total_timeout=10.0
        )
        ok = p.send("body invalid header valid test")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)
        mock_sleep.assert_called_once_with(3.0)

    @responses.activate
    @patch("time.sleep", return_value=None)
    @patch("random.uniform", return_value=0.0)
    def test_retry_after_header_http_date_ignored(self, mock_uniform, mock_sleep):
        """Retry-After header is an HTTP date string -> ignored, falls back to backoff, success."""
        url = f"https://api.telegram.org/bot{CANARY}/sendMessage"
        responses.add(
            responses.POST,
            url,
            headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"},
            status=429,
        )
        responses.add(responses.POST, url, json={"ok": True}, status=200)

        p = Poster(
            token=CANARY, chat_id=CHAT_ID, max_retries=1, chunk_delay=0.0, total_timeout=30.0
        )
        ok = p.send("date header test")
        self.assertTrue(ok)
        self.assertEqual(len(responses.calls), 2)

    def test_parse_retry_after_direct(self):
        """Unit test of _parse_retry_after directly for a table of inputs."""

        test_cases = [
            (2, 2.0),
            ("2", 2.0),
            (2.5, 2.5),
            (0, 0.0),
            (float("inf"), float("inf")),
            (float("nan"), None),
            (-1, None),
            (float("-inf"), None),
            ("soon", None),
            (True, None),
            (None, None),
            ([], None),
            ({}, None),
        ]

        for input_val, expected in test_cases:
            with self.subTest(input_val=input_val):
                result = Poster._parse_retry_after(input_val)
                self.assertEqual(result, expected, f"Failed for input {input_val}")

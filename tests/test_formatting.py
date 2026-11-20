import unittest
from post_on_telegram.formatting import escape_html, escape_markdown_v2, format_pre


class TestFormatting(unittest.TestCase):
    def test_escape_html(self):
        self.assertEqual(escape_html("a & b < c > d"), "a & b < c > d")

    def test_escape_markdown_v2(self):
        self.assertEqual(escape_markdown_v2("_*[]()~`>#+-=|{}.!\\"),
                         "\\_\\*\\[\\]\\(\\)\\~\\`\\>\\#\\+\\-\\=\\|\\{\\}\\.\\!\\\\")

    def test_format_pre(self):
        result = format_pre("a < b")
        self.assertEqual(result, "<pre>a < b</pre>")
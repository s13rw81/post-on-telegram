import unittest

from post_on_telegram.formatting import escape_html, escape_markdown_v2, format_pre


class TestFormatting(unittest.TestCase):
    def test_escape_html(self):
        self.assertEqual(escape_html("a & b < c > d"), "a &amp; b &lt; c &gt; d")

    def test_escape_markdown_v2(self):
        # Escape all MarkdownV2 special characters: _ * [ ] ( ) ~ ` > # + - = | { } . ! and \
        chars = "_*[]()~`>#+-=|{}.!\\"
        expected = "".join(f"\\{c}" for c in chars)
        self.assertEqual(escape_markdown_v2(chars), expected)

    def test_format_pre(self):
        result = format_pre("a < b")
        self.assertEqual(result, "<pre>a &lt; b</pre>")

import unittest
from post_on_telegram.chunking import chunk_text


class TestChunking(unittest.TestCase):
    def test_short_text_single_chunk(self):
        self.assertEqual(chunk_text("hello", 100), ["hello"])

    def test_exactly_max_length(self):
        text = "a" * 100
        chunks = chunk_text(text, 100)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)

    def test_max_plus_one(self):
        text = "a" * 101
        chunks = chunk_text(text, 100)
        self.assertEqual(len(chunks), 2)
        self.assertEqual("".join(chunks), text)

    def test_10k_no_whitespace(self):
        text = "a" * 10000
        chunks = chunk_text(text, 1000)
        self.assertEqual(len(chunks), 10)
        self.assertEqual("".join(chunks), text)
        for c in chunks:
            self.assertLessEqual(len(c), 1000)

    def test_many_short_paragraphs(self):
        text = "\n\n".join(["para"] * 100)
        chunks = chunk_text(text, 100)
        self.assertEqual("".join(chunks).replace("\n", ""), text.replace("\n", ""))
        for c in chunks:
            self.assertLessEqual(len(c), 100)

    def test_emoji_multibyte(self):
        text = "😀" * 500
        chunks = chunk_text(text, 100)
        self.assertEqual("".join(chunks), text)
        for c in chunks:
            self.assertLessEqual(len(c), 100)

    def test_no_empty_chunks(self):
        text = "a" * 1000
        chunks = chunk_text(text, 100)
        for c in chunks:
            self.assertTrue(c)

    def test_order_preserved(self):
        text = "abcdefghij" * 100
        chunks = chunk_text(text, 50)
        self.assertEqual("".join(chunks), text)

    def test_whitespace_only(self):
        chunks = chunk_text("   \n\n   ", 10)
        self.assertEqual("".join(chunks).strip(), "")

    def test_newlines_only(self):
        chunks = chunk_text("\n" * 100, 10)
        self.assertEqual("".join(chunks).strip(), "")

    def test_invalid_max_length(self):
        with self.assertRaises(ValueError):
            chunk_text("hello", 0)

    def test_prefers_blank_line(self):
        text = "a" * 50 + "\n\n" + "b" * 50
        chunks = chunk_text(text, 60)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].endswith("a"))

    def test_prefers_newline(self):
        text = "a" * 50 + "\n" + "b" * 50
        chunks = chunk_text(text, 60)
        self.assertEqual(len(chunks), 2)

    def test_prefers_space(self):
        text = "a" * 50 + " " + "b" * 50
        chunks = chunk_text(text, 60)
        self.assertEqual(len(chunks), 2)
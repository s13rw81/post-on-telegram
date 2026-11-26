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
        # Prefixes [1/2] and [2/2] are 6 chars each
        self.assertTrue(chunks[0].startswith("[1/2] "))
        self.assertTrue(chunks[1].startswith("[2/2] "))
        for c in chunks:
            self.assertLessEqual(len(c), 100)
        # Re-joining content preserves text
        combined = chunks[0][6:] + chunks[1][6:]
        self.assertEqual(combined, text)

    def test_10k_no_whitespace(self):
        text = "a" * 10000
        chunks = chunk_text(text, 1000)
        for i, c in enumerate(chunks, start=1):
            self.assertLessEqual(len(c), 1000)
            prefix = f"[{i}/{len(chunks)}] "
            self.assertTrue(c.startswith(prefix))

    def test_many_short_paragraphs(self):
        paras = [f"Paragraph {i}" for i in range(50)]
        text = "\n\n".join(paras)
        chunks = chunk_text(text, 200)
        for c in chunks:
            self.assertLessEqual(len(c), 200)
        self.assertGreater(len(chunks), 1)

    def test_emoji_multibyte(self):
        text = "😀🎉🚀" * 100
        chunks = chunk_text(text, 100)
        for c in chunks:
            self.assertLessEqual(len(c), 100)

    def test_no_empty_chunks(self):
        text = "a" * 1000
        chunks = chunk_text(text, 100)
        for c in chunks:
            self.assertTrue(len(c) > 0)

    def test_order_preserved(self):
        text = "abcdefghijklmnopqrstuvwxyz" * 20
        chunks = chunk_text(text, 50)
        reconstructed = "".join(c[c.index(" ") + 1 :] for c in chunks)
        self.assertEqual(reconstructed, text)

    def test_invalid_max_length(self):
        with self.assertRaises(ValueError):
            chunk_text("hello", 0)

    def test_prefers_blank_line(self):
        part1 = "a" * 30
        part2 = "b" * 30
        text = part1 + "\n\n" + part2
        chunks = chunk_text(text, 50)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].endswith("\n\n"))

    def test_prefers_newline(self):
        part1 = "a" * 30
        part2 = "b" * 30
        text = part1 + "\n" + part2
        chunks = chunk_text(text, 50)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].endswith("\n"))

    def test_chunk_empty_text(self):
        self.assertEqual(chunk_text("", 100), [])

    def test_chunking_surrogate_and_combining(self):
        # Base character with combining accent: 'e' + '\u0301'
        combining_str = "e\u0301" * 10
        chunks = chunk_text(combining_str, 5)
        for c in chunks:
            self.assertTrue(len(c) > 0)
        part1 = "a" * 30
        part2 = "b" * 30
        text = part1 + " " + part2
        chunks = chunk_text(text, 50)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].endswith(" "))

    def test_whitespace_only_slices_dropped(self):
        """'x' + ' '*10000 + 'y' yields no whitespace-only chunk and no lost non-whitespace text."""
        text = "x" + " " * 10000 + "y"
        chunks = chunk_text(text, 100)
        # No chunk should be whitespace-only
        for c in chunks:
            self.assertTrue(c.strip(), f"Chunk is whitespace-only: {repr(c)}")
        # All non-whitespace text should be preserved
        combined = "".join(chunks)
        self.assertIn("x", combined)
        self.assertIn("y", combined)

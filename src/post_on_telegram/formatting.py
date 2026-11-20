# src/post_on_telegram/formatting.py
"""Text formatting helpers for Telegram messages."""


def escape_html(text: str) -> str:
    """Escape HTML special characters: &, <, >.

    Args:
        text: The text to escape.

    Returns:
        The text with &, <, > escaped as HTML entities.
    """
    text = text.replace("&", "&")
    text = text.replace("<", "<")
    text = text.replace(">", ">")
    return text


def escape_markdown_v2(text: str) -> str:
    """Escape all MarkdownV2 special characters.

    Characters escaped: _ * [ ] ( ) ~ ` > # + - = | { } . ! and backslash.

    Args:
        text: The text to escape.

    Returns:
        The text with MarkdownV2 special characters escaped.
    """
    chars_to_escape = r"_*[]()~`>#+-=|{}.!\\"
    escape_table = str.maketrans({c: f"\\{c}" for c in chars_to_escape})
    return text.translate(escape_table)


def format_pre(text: str) -> str:
    """Format text as a monospace code block (HTML <pre> tag).

    Intended for use with parse_mode="HTML".

    Args:
        text: The text to format.

    Returns:
        The text wrapped in <pre> tags with HTML-escaped content.
    """
    escaped = escape_html(text)
    return f"<pre>{escaped}</pre>"
</write_to_file>
<task_progress>
- [x] Create project directory structure
- [x] Write _version.py
- [x] Create __init__.py placeholder
- [x] Create pyproject.toml
- [x] Write LICENSE
- [x] Write README.md
- [x] Create .gitignore
- [x] Create .editorconfig
- [x] Create CONTRIBUTING.md
- [x] Create SECURITY.md
- [x] Create CHANGELOG.md
- [x] Implement formatting.py
- [x] Implement errors.py
- [x] Implement chunking.py
- [x] Implement credentials.py
- [x] Implement poster.py
- [x] Implement cli.py
- [x] Implement __main__.py
- [x] Create py.typed
- [x] Write examples
- [x] Write tests/test_credentials.py
- [x] Write tests/test_chunking.py
- [x] Write tests/test_formatting.py
- [x] Write tests/test_poster.py
- [x] Write tests/test_cli.py
- [x] Write tests/test_readme_examples.py
- [ ] Write CI/CD workflows
- [ ] Write issue/PR templates
- [ ] Create examples/credentials.example.json
- [ ] Verify build and packaging
- [ ] Run tests, coverage, linting, mypy
- [ ] Create wheel and sdist, verify contents
- [ ] Test in fresh venv
</task_progress>
</write_to_file>
</tool_call>
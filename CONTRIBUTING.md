# Contributing to Post on Telegram

Thank you for your interest in contributing!

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

## Code style

- Run `python -m ruff check .` and `python -m ruff format --check .`.
- Run `python -m mypy src` for type checking.

## Tests

```bash
python -m pytest --cov=post_on_telegram
```

## Pull requests

- Follow the PR template.
- Ensure CI passes.
- Add tests for new features.

## Release process

1. Bump version in `src/post_on_telegram/_version.py`.
2. Update `CHANGELOG.md`.
3. Tag `vX.Y.Z`.
4. CI publishes via PyPI Trusted Publishing.
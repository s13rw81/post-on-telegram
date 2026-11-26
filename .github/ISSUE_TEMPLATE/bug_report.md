---
name: Bug Report
description: Create a report to help us improve post-on-telegram
title: "[BUG] "
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: |
        **WARNING: Never include your Telegram bot token or chat ID!**
        Remove or redact any token and chat ID before pasting logs or commands.
  - type: input
    id: package_version
    attributes:
      label: Package version
      description: The version of post-on-telegram (`post-on-telegram --version`)
      placeholder: e.g. 0.1.0
    validations:
      required: true
  - type: input
    id: python_version
    attributes:
      label: Python version
      description: What version of Python are you running? (`python --version`)
      placeholder: e.g. 3.11.4
    validations:
      required: true
  - type: input
    id: os
    attributes:
      label: Operating System
      description: Which operating system and version are you using?
      placeholder: e.g. Windows 11, Ubuntu 22.04, macOS Sonoma
    validations:
      required: true
  - type: textarea
    id: reproduction
    attributes:
      label: Minimal code / CLI command
      description: Provide a minimal, reproducible code sample or command (with tokens removed).
      placeholder: |
        ```python
        from post_on_telegram import Poster

        poster = Poster(...)
        ```
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: Expected behaviour
      description: What did you expect to happen?
    validations:
      required: true
  - type: textarea
    id: actual
    attributes:
      label: Actual behaviour and log output
      description: |
        What happened instead? Paste the log output or traceback below.
        **CHECK AGAIN**: ensure your bot token and chat ID have been completely removed!
    validations:
      required: true

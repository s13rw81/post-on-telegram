# Security Policy

## Supported versions

Only the latest released version of Post on Telegram is supported with security
fixes.

## Reporting a vulnerability

If you discover a security vulnerability, please report it privately to the
maintainer. Do **not** open a public issue.

## Best practices

- Keep your bot token secret. Use environment variables or a credentials file
  with restrictive permissions (`chmod 600` on Linux/macOS).
- Rotate your token immediately if you suspect it has been leaked, using
  `/revoke` in @BotFather.
- Never commit credentials files or tokens to version control.
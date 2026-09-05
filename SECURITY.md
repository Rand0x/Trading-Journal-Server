# Security Policy

## Supported Versions

Security fixes are provided for the current state of the `main` branch.

## Reporting a Vulnerability

Do not disclose credentials, Journal API keys, database contents, or reproducible
exploit code in a public issue. Instead, use the private vulnerability reporting
feature of the hosting platform if enabled, or contact the repository owner
via a private channel.

## Operating Securely

- The Docker configuration binds the service to `127.0.0.1` by default.
  Set `HOST_BIND_ADDRESS=0.0.0.0` deliberately only when access from trusted
  LAN devices is required.
- HTTP Basic Auth can be enabled for the web interface using `JOURNAL_USERNAME`
  and `JOURNAL_PASSWORD`.
- The MT4/MT5 and cTrader push endpoints are excluded from Basic Auth because
  they are authenticated via their individual, per-account Journal API key.
- Never commit or share Journal API keys, cTrader client secrets, access tokens,
  or the contents of `data/journal.db` in repositories, chats, or screenshots.
- For access outside the local network, use a VPN or an HTTPS reverse proxy
  with additional access control.

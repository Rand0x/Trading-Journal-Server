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

## Publication Gate

Before publishing a repository or uploading a source archive:

1. Review tracked, untracked and ignored files (`git ls-files`,
   `git ls-files --others --exclude-standard`, and
   `git ls-files --others --ignored --exclude-standard`). Never upload the whole
   working directory: ignored databases, screenshots and local configuration
   are still present on disk. Do not force-add them.
2. Scan both the working tree and **all reachable history**, for example with
   a trusted Gitleaks installation:
   ```sh
   gitleaks git . --log-opts="--all --full-history" --redact=100
   gitleaks dir . --redact=100
   ```
   Keep any reports outside the repository. A clean scanner result is not proof
   of absence: review low-entropy passwords, private network/deployment details,
   connection URLs, database files and synthetic test credentials separately.
3. Check `.gitignore` and `.dockerignore`: they do not remove files already
   tracked by Git or historical objects. Use a reviewed source-only archive or
   the Docker build context, not an unrestricted recursive upload.
4. If a real credential was committed, revoke/rotate it first. Removing it in a
   new commit does not remove the exposure. Obtain explicit owner approval for
   history cleanup, coordinate affected clones and hosting caches, and rescan
   every ref before publication. Never rewrite shared history automatically.
5. Resolve historical private deployment identifiers before a public push, or
   obtain an explicit decision from the owner to publish those identifiers.
   Ordinary Git author metadata is also public; review it without copying
   private email addresses into public audit reports.

Local `data/`, `scratch/`, `backups/`, `secrets/`, environment files and private
key files are intentionally excluded. `.env.example` must contain placeholders
only. Synthetic test keys are not production credentials and must never be
reused for deployment.

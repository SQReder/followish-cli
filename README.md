# followish-cli

Command-line client for [Followish](https://followish.io) wishlists, built to be driven by AI agents:
every command prints JSON, every command has a descriptive `--help`, errors are JSON with distinct exit codes.

Python 3.10+, standard library only.

## Setup

```sh
cp .env.example .env        # fill in FOLLOWISH_EMAIL and FOLLOWISH_PASSWORD
python followish.py --help
# or install the `followish` command:
uv tool install .           # or: pipx install .
```

Credentials come from environment variables `FOLLOWISH_EMAIL` / `FOLLOWISH_PASSWORD` or from `./.env`
(environment wins; `--env-file PATH` points elsewhere). Login is automatic; the session cookie is cached
in `~/.cache/followish` (`FOLLOWISH_CACHE_DIR` overrides) and renewed when the server returns 401.
Only email/password accounts work: social-login accounts need a password set on the site first.

## Commands

```
followish auth      login | logout | whoami
followish wishlists list | get KEY | create --name ... | update KEY ... | delete KEY
followish presents  get ID | add KEY --name ... | update ID ... | delete ID
                    done ID [--undo] | move ID --to KEY | friends | unreserve ID
followish friends   list | add USER_LINK | remove FRIEND_ID
followish profile   get USER_LINK | wishlists USER_LINK
followish api       METHOD PATH [--json BODY]      # any other endpoint
```

`followish <group> <command> --help` explains arguments and defaults.

## Output contract

- Success: the API response JSON on stdout, exit code 0.
- Failure: `{"error": {"type": ..., "message": ..., "status"?: ..., "body"?: ...}}` on stdout and exit code
  `1` (API/network), `2` (invalid arguments), `3` (missing credentials or rejected login).

## Limitations

- Followish has no public API. The client uses the private API of the web app
  (`https://core.followish.io/api`), recovered from its frontend bundle; it can change without notice.
- Reserving a friend's gift is not supported: the site signs that request with an anti-bot token.
- Secret Santa, chats, business and admin features are not wrapped; reach them through `followish api`.

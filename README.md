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
(environment wins; `--env-file PATH` points elsewhere). Login is automatic; the bearer access token is cached
in `~/.cache/followish` (`FOLLOWISH_CACHE_DIR` overrides, file mode 0600) and renewed when the server returns 401.
The token is never printed; `auth login` returns only the user.
Only email/password accounts work: social-login accounts need a password set on the site first.

## Commands

```
followish auth      login | logout | whoami
followish wishlists list | get KEY | create --name ... | update KEY ... | delete KEY
followish presents  get ID | add KEY --name ... | update ID ... | delete ID
                    done ID [--undo] | fulfilled | move ID --to KEY | friends | unreserve ID
followish friends   list | add USER_LINK | remove FRIEND_ID
followish profile   get USER_LINK | wishlists USER_LINK
followish api       METHOD PATH [--json BODY]      # any other endpoint
```

`followish <group> <command> --help` explains arguments and defaults.

`KEY`, `ID` and `USER_LINK` also accept followish.io URLs, e.g. `followish wishlists get https://followish.io/mywishlist/niepglsrgxbuhn`.

## For agents

- Using the CLI: install the skill from [`skills/followish/SKILL.md`](skills/followish/SKILL.md) by copying the
  `skills/followish` directory into your agent's skills directory, e.g. for Claude Code:
  `cp -r skills/followish ~/.claude/skills/` (or `~/.claude/skills/` → `.claude/skills/` for one project).
- Changing this repository: read [`AGENTS.md`](AGENTS.md).

## Checks

`python test_followish.py` (or `python -m pytest`).

End-to-end check against the live account: `python e2e.py`. It creates two private (`justMe`) wishlists named
`followish-cli e2e ...`, runs create/get/add/update/move/done/undo/delete and error cases through the CLI, and deletes
everything afterwards (leftovers of a crashed run are swept at the next start). Each call waits a random 3–8 s pause
to look like a person; tune with `FOLLOWISH_E2E_PAUSE=min-max`. Takes about 3 minutes.

## Output contract

- Success: `{"result": ..., "hints": [...]}` on stdout, exit code 0.
  - `result` keeps only the fields an agent normally needs, named like the CLI arguments
    (`key`, `id`, `userLink`, `link`, `view`, `reserved`, `done`...); null and empty fields are omitted.
  - `hints` lists the next useful commands with `KEY` / `ID` / `USER_LINK` placeholders and the relevant `--help`.

  ```json
  {"result": [{"key": "fm5uc5oy6menux", "name": "2026", "presentsCount": 11, "dateEnd": "2026-10-05"}],
   "hints": ["followish wishlists get KEY — settings and presents of a wishlist", "..."]}
  ```
- `--raw` (global, before the group: `followish --raw wishlists list`) prints the unmodified API response
  with API field names (`linkKey`, `storeLink`...). `followish api` always prints raw.
- Failure: `{"error": {"type": ..., "message": ..., "status"?: ..., "body"?: ...}}` on stdout and exit code
  `1` (API/network), `2` (invalid arguments), `3` (missing credentials or rejected login).

## Limitations

- Followish has no public API. The client uses the private API of the web app
  (`https://core.followish.io/api`), recovered from its frontend bundle; it can change without notice.
- Reserving a friend's gift is not supported: the site signs that request with an anti-bot token.
- Secret Santa, chats, business and admin features are not wrapped; reach them through `followish api`.

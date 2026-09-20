# 🎁 followish-cli

**Your wishlist, but your AI agent does the typing.**

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![Dependencies: zero](https://img.shields.io/badge/dependencies-zero-brightgreen)
![Output: JSON](https://img.shields.io/badge/output-JSON-orange)
![Built for: agents](https://img.shields.io/badge/built%20for-agents-blueviolet)
[![License: WTFPL](https://img.shields.io/badge/license-WTFPL-red)](LICENSE)

Filling in wishlist cards by hand is boring. Telling an agent "add that keyboard I keep talking about" is not.

`followish-cli` is a command-line client for [Followish](https://followish.io) wishlists, built to be driven by
AI agents rather than humans: every command prints JSON, every command has a descriptive `--help`, and errors are
JSON with distinct exit codes. One file, Python 3.10+, standard library only.

## ✨ The trick: every answer says what to do next

An agent should not have to memorise a CLI. So each successful response carries `hints`: the next useful
commands for the data it just received.

```sh
$ followish wishlists list
```

```json
{"result": [{"key": "fm5uc5oy6menux", "name": "2026", "presentsCount": 11, "dateEnd": "2026-10-05"}],
 "hints": ["followish wishlists get KEY — settings and presents of a wishlist",
           "followish presents add KEY --name ... — add a present",
           "followish wishlists update KEY ... | delete KEY",
           "..."]}
```

Got the wishlists? The response already says you can look inside one, add a present or edit its settings.
Follow a hint, get a new `result` with new `hints`, repeat. The agent walks the whole API without reading
the docs first.

## 🚀 Quick start

```sh
cp .env.example .env        # fill in FOLLOWISH_EMAIL and FOLLOWISH_PASSWORD
python followish.py --help
# or install the `followish` command:
uv tool install .           # or: pipx install .
```

Then point your agent at it:

```sh
cp -r skills/followish ~/.claude/skills/    # Claude Code; use .claude/skills/ for a single project
```

The skill lives in [`skills/followish/SKILL.md`](skills/followish/SKILL.md); for other agents, copy the
`skills/followish` directory into their skills directory. No skill support? `followish --help` tells an agent
everything it needs, and it ends with "Start with: followish wishlists list".

### Credentials

They come from environment variables `FOLLOWISH_EMAIL` / `FOLLOWISH_PASSWORD` or from `./.env`
(environment wins; `--env-file PATH` points elsewhere). Login is automatic; the bearer access token is cached
in `~/.cache/followish` (`FOLLOWISH_CACHE_DIR` overrides, file mode 0600) and renewed when the server returns 401.
The token is never printed; `auth login` returns only the user.
Only email/password accounts work: social-login accounts need a password set on the site first.

## 🧰 Commands

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

`KEY`, `ID` and `USER_LINK` also accept followish.io URLs, so you can paste a link straight from the browser:
`followish wishlists get https://followish.io/mywishlist/niepglsrgxbuhn`.

## 📜 Output contract

- Success: `{"result": ..., "hints": [...]}` on stdout, exit code 0.
  - `result` keeps only the fields an agent normally needs, named like the CLI arguments
    (`key`, `id`, `userLink`, `link`, `view`, `reserved`, `done`...); null and empty fields are omitted.
  - `hints` lists the next useful commands with `KEY` / `ID` / `USER_LINK` placeholders and the relevant `--help`.
- `--raw` (global, before the group: `followish --raw wishlists list`) prints the unmodified API response
  with API field names (`linkKey`, `storeLink`...). `followish api` always prints raw.
- `--pretty` (global) indents the JSON for the occasional human.
- Failure: `{"error": {"type": ..., "message": ..., "status"?: ..., "body"?: ...}}` on stdout and exit code
  `1` (API/network), `2` (invalid arguments), `3` (missing credentials or rejected login).

## ⚠️ Limitations

- Followish has no public API. The client uses the private API of the web app
  (`https://core.followish.io/api`), recovered from its frontend bundle; it can change without notice.
- Reserving a friend's gift is not supported: the site signs that request with an anti-bot token.
- Secret Santa, chats, business and admin features are not wrapped; reach them through `followish api`.

## 🛠️ Hacking on it

Read [`AGENTS.md`](AGENTS.md) first: layout, private API facts and the pitfalls already hit.

Offline checks: `python test_followish.py` (or `python -m pytest`).

End-to-end check against the live account: `python e2e.py`. It creates two private (`justMe`) wishlists named
`followish-cli e2e ...`, runs create/get/add/update/move/done/undo/delete and error cases through the CLI, and deletes
everything afterwards (leftovers of a crashed run are swept at the next start). Each call waits a random 3–8 s pause
to look like a person; tune with `FOLLOWISH_E2E_PAUSE=min-max`. Takes about 3 minutes.

## 📄 License

[WTFPL](LICENSE): do what you want with it.

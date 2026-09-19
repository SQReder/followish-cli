# AGENTS.md

Guide for agents changing this repository. To *use* the CLI, read [`skills/followish/SKILL.md`](skills/followish/SKILL.md).

## What this is

`followish.py` is a single-file, stdlib-only (Python 3.10+) CLI for the followish.io wishlist service, built to be
driven by AI agents. Followish has no public API: the client talks to the private web-app API at
`https://core.followish.io/api`, recovered from the site's frontend bundle.

| File | Purpose |
|---|---|
| `followish.py` | The whole CLI: HTTP client, command handlers, output views, argument parser |
| `test_followish.py` | Offline table checks (URL → identifier parsing) |
| `e2e.py` | Live end-to-end run against the account from `.env`; self-cleaning, slow on purpose |
| `skills/followish/` | Installable skill for agents that use the CLI |

## Commands

```sh
python test_followish.py        # offline checks, seconds
python e2e.py                   # live account, ~3 min, creates and deletes private test wishlists
python followish.py --help      # every group and command has --help
```

Credentials: `FOLLOWISH_EMAIL` / `FOLLOWISH_PASSWORD` in the environment or `./.env` (git-ignored; never commit it).
Run `e2e.py` after any change to a handler, a view or the HTTP client. It pauses 3–8 s before every call so the
traffic does not look like a bot; keep that when adding steps, and do not hammer the live API in loops.

## Layout of `followish.py`

1. **Client** — logs in with email/password, caches the bearer `access_token` per account in `~/.cache/followish`,
   re-logs in once on HTTP 401. Never print the token.
2. **Handlers** `cmd_<group>_<command>(client, args)` — call the API and return the raw response.
3. **Views** — pure functions raw response → compact dict for `result`. Field names follow the CLI arguments
   (`key`, `id`, `userLink`, `link`, `view`, `reserved`, `done`), not the API names.
4. **Parser** — `command(parent, name, handler, help, description, view=..., hints=(...))`. `main()` wraps the view
   output as `{"result": ..., "hints": [...]}`, drops null/empty fields, and prints raw data with `--raw`.

### Adding a command

- Write the handler; reuse `cmd_wishlists_get` / `pick` / `present_form` instead of re-implementing request shapes.
- Give it a `view` (never pass the raw response through) and 1–4 `hints` with `KEY` / `ID` / `USER_LINK`
  placeholders plus the group `--help`. Mutations use `ok(...)` to echo identifiers.
- Identifier arguments use `type=wishlist_key` / `present_id` / `user_link`, so URLs are accepted.
- Write the `help` and `description` for an agent that has never seen the site: what it does, defaults,
  an example, what is irreversible.
- Update `README.md`, `CHANGELOG.md` (Keep a Changelog), the skill, and `e2e.py` if the command is safe to run on
  private test data.

## Private API facts (verified live, easy to get wrong)

- Auth is `Authorization: Bearer <access_token>` from `POST /auth/login`; the `token` cookie alone gives 401.
- Wishlists are addressed by `linkKey` everywhere **except** `DELETE /wishlists/{id}`, which takes the numeric id
  (the key gives 405).
- `POST /wishlists/{key}` with `{"isPublicPage": false}` reads a wishlist, including friends' wishlists.
- Presents are created and edited as `multipart/form-data`; the response field `image` is sent back as `imageLink`.
- Dates are sent as `DD.MM.YYYY` and come back as `YYYY-MM-DD 00:00:00` or ISO with `T00:00:00Z`.
- With the account setting `moveToExecutedSection`, `setWishExecuted` moves the present into a hidden wishlist
  (`isExecutedSection`), whose key is only in the owner's `GET /profile/{userLink}` → `executedSection`.
- Reserving a friend's present (`PUT /presents/{id}/reserve`) is signed with an anti-bot HMAC; not supported.
- The server rate-limits (`x-ratelimit-limit: 20` observed on login).
- Endpoint names and payloads come from the frontend bundle (`https://followish.io/_next/static/...`): search it
  for `.W.post("/...` to find a call and its body before guessing.

## Pitfalls already hit

- An argparse `dest` must not collide with `set_defaults` keys: `--view` once overwrote the output view
  (it is stored as `render` now).
- Read-modify-write updates (`wishlists update`, `presents update`) send every field the site sends. A partial
  body was never tested; assume the server may reset missing fields (the image was dropped before `imageLink`
  was mapped back).
- A handler that crashes after a successful request leaves live data behind; check `wishlists list` and clean up.

## Conventions

- Stdlib only; no new dependencies without a strong reason.
- Commits: Conventional Commits in English. Branch per change, PR into `main`, rebase-merge.
- Destructive calls against the live account (delete, friends, reservations) only on data you created,
  or with the owner's explicit confirmation.

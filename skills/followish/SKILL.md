---
name: followish
description: Use when the user asks to read or manage their Followish (followish.io) wishlists, gifts, fulfilled wishes, friends or reservations, or hands you a followish.io link — covers the `followish` CLI, its JSON output and pitfalls.
---

# Followish CLI

`followish` manages wishlists on followish.io from the command line. Output is JSON built for agents.

## Setup (once)

```sh
uv tool install git+https://github.com/SQReder/followish-cli   # or: pipx install git+https://github.com/SQReder/followish-cli
```

Credentials: `FOLLOWISH_EMAIL` and `FOLLOWISH_PASSWORD` in the environment, or a `.env` file in the **current
directory**, or `followish --env-file PATH ...`. Never print or log them. Login is automatic and cached.
Without credentials every command exits 3 with `missing_credentials` — ask the user, do not guess.

## Output contract

```json
{"result": ..., "hints": ["followish wishlists get KEY — ...", "..."]}
```

- `result`: only useful fields, named like CLI arguments; missing field = empty/not set.
- `hints`: sensible next commands; substitute `KEY` / `ID` / `USER_LINK` from `result`.
- Errors: `{"error": {"type", "message", "status"?, "body"?}}`; exit `1` API/network, `2` bad arguments
  (read `usage`), `3` credentials/login.
- `followish --raw <group> <command>` (flag **before** the group) prints the unmodified API response.

## Identifiers

| Thing | Argument | Where to get it | URL also accepted |
|---|---|---|---|
| Wishlist | `KEY` | `wishlists list` → `key` | `https://followish.io/mywishlist/KEY` |
| Present | `ID` | `wishlists get KEY` → `presents[].id` | `.../presents/ID/...` |
| User | `USER_LINK` | `friends list` → `userLink` | `https://followish.io/app/users/USER_LINK` |

Pass links from the user straight through; the CLI extracts the identifier.

## Tasks → commands

| Task | Command |
|---|---|
| Who am I / check access | `followish auth whoami` |
| My wishlists | `followish wishlists list` (`presentsCount`, `dateEnd`) |
| Presents in a wishlist (mine or a friend's) | `followish wishlists get KEY` |
| Full present (description, link, image) | `followish presents get ID` |
| Create wishlist | `followish wishlists create --name ... [--date-end YYYY-MM-DD] [--view all\|friends\|justMe\|selectedFriends]` |
| Change wishlist settings | `followish wishlists update KEY --view friends` (only passed options change) |
| Add present | `followish presents add KEY --name ... [--price 4990] [--currency RUB] [--link URL] [--description ...] [--desire N]` |
| Edit present | `followish presents update ID --price ...` (only passed fields change) |
| Mark wish fulfilled / undo | `followish presents done ID` / `followish presents done ID --undo` |
| Fulfilled presents | `followish presents fulfilled` (they may vanish from their wishlist after `done`) |
| Move present | `followish presents move ID --to KEY` |
| Gifts I reserved for friends | `followish presents friends`; cancel: `followish presents unreserve ID` |
| Friends, birthdays, requests | `followish friends list` |
| A friend's wishlists | `followish profile wishlists USER_LINK`, then `wishlists get KEY` |
| Anything else | `followish api METHOD /path [--json BODY]` (raw, undocumented private API) |

Every group and command has `--help` with arguments, defaults and, where useful, an example:
`followish presents add --help`. `--view selectedFriends` also needs `--allowed-friend-ids ID ...` (ids from
`friends list`).

## Rules

- **Confirm with the user before** `wishlists delete` (removes all its presents), `presents delete`,
  `friends add/remove`, `presents unreserve`. They are irreversible or visible to other people.
- **Reserving a friend's gift is not possible** from the CLI (anti-bot signature). Send the user the wishlist link.
- Prices are strings of digits; dates in and out are `YYYY-MM-DD`; `--date-end none` clears the date.
- Wishlists you create for experiments: use `--view justMe` so friends do not see them.
- The API is private and rate-limited: no tight loops, no bulk scraping; batch reads from one `wishlists get`.
- If a field you need is missing from `result`, rerun with `--raw` instead of guessing.

## Common mistakes

| Mistake | Fix |
|---|---|
| `followish wishlists list --raw` | `followish --raw wishlists list` |
| Looking for a fulfilled present in `wishlists list` | `followish presents fulfilled` |
| Passing the numeric wishlist id | Use `key` (or the wishlist URL) |
| `.env` not found after `uv tool install` | Run from the directory with `.env`, use `--env-file`, or export the variables |

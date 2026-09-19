# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- JSON-first CLI for followish.io: auth, wishlists, presents, friends, profile commands and a raw `api` escape hatch.
- Email/password login from environment variables or `.env`, with a cached per-account access token.
- Wishlist keys, present ids and user links also accept followish.io URLs.
- `e2e.py`: self-cleaning end-to-end check against the live account, with human-like pauses between calls.

### Changed

- Output is now `{"result", "hints"}`: `result` keeps only the relevant fields under CLI-style names and drops
  empty ones; `hints` suggests next commands. Use the global `--raw` flag for the unmodified API response.

### Fixed

- Every authenticated command returned HTTP 401: the API expects a bearer token, not the session cookie.
- `presents update` no longer drops the present image.
- `auth login` no longer prints the access token.
- `wishlists delete` failed with HTTP 405: the API deletes wishlists by numeric id, not by key.
- `wishlists create` / `update` with `--view` crashed after the request succeeded.

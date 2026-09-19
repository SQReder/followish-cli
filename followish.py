"""Command-line client for Followish (https://followish.io), built for AI agents.

Every command prints JSON to stdout. Exit codes: 0 ok, 1 API/network error,
2 usage error, 3 missing credentials or failed login.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

API_BASE = "https://core.followish.io/api"
SITE = "https://followish.io"
SERVER_DATE_FORMAT = "%d.%m.%Y"
CURRENCIES = "RUB, BYN, KZT, KGS, EUR, USD, GBP, AUD, CAD, AMD, AZN, AED and others supported by the site"

EXIT_API, EXIT_USAGE, EXIT_AUTH = 1, 2, 3

# Fields the site sends when saving a wishlist or a present; used for read-modify-write updates.
WISHLIST_FIELDS = ("name", "comment", "dateEnd", "nameVisibleStatus", "viewPrivacyStatus",
                   "reservePrivacyStatus", "isProfileLinkVisible", "theme", "allowedFriendIds")
PRESENT_FIELDS = ("name", "currency", "desireLevel", "price", "description", "imageLink", "storeLink")


class CliError(Exception):
    def __init__(self, code: int, kind: str, message: str, **extra: object) -> None:
        super().__init__(message)
        self.code, self.kind, self.extra = code, kind, extra


def emit(payload: object, pretty: bool) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None))


# ---------------------------------------------------------------- credentials

def load_dotenv(path: pathlib.Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def credentials(env_file: str | None) -> tuple[str, str]:
    dotenv = load_dotenv(pathlib.Path(env_file or ".env"))
    # Real environment variables win over .env.
    email = os.environ.get("FOLLOWISH_EMAIL") or dotenv.get("FOLLOWISH_EMAIL")
    password = os.environ.get("FOLLOWISH_PASSWORD") or dotenv.get("FOLLOWISH_PASSWORD")
    if not email or not password:
        raise CliError(EXIT_AUTH, "missing_credentials",
                       "Set FOLLOWISH_EMAIL and FOLLOWISH_PASSWORD in the environment or in .env")
    return email, password


# ---------------------------------------------------------------- HTTP client

def multipart(fields: dict[str, object]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n')
    parts.append(f"--{boundary}--\r\n")
    return "".join(parts).encode("utf-8"), f"multipart/form-data; boundary={boundary}"


class Client:
    def __init__(self, env_file: str | None) -> None:
        self.env_file = env_file
        self._creds: tuple[str, str] | None = None
        email = self.creds[0]
        cache_dir = pathlib.Path(os.environ.get("FOLLOWISH_CACHE_DIR", pathlib.Path.home() / ".cache" / "followish"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        # One token file per account, so switching FOLLOWISH_EMAIL never reuses another user's session.
        account = hashlib.sha256(email.lower().encode()).hexdigest()[:16]
        self.token_file = cache_dir / f"token-{account}"
        self.token = self.token_file.read_text(encoding="utf-8").strip() if self.token_file.is_file() else None

    def _save_token(self, token: str | None) -> None:
        self.token = token
        if token is None:
            self.token_file.unlink(missing_ok=True)
            return
        fd = os.open(self.token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(token)

    @property
    def creds(self) -> tuple[str, str]:
        if self._creds is None:
            self._creds = credentials(self.env_file)
        return self._creds

    def _send(self, method: str, path: str, body: object = None, form: dict | None = None) -> tuple[int, object]:
        headers = {"Accept": "application/json", "x-platform": "web", "Origin": SITE, "Referer": SITE + "/",
                   "User-Agent": "followish-cli/0.1"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = None
        if form is not None:
            data, headers["Content-Type"] = multipart(form)
        elif body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        request = urllib.request.Request(API_BASE + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as err:
            status, raw = err.code, err.read()
        except urllib.error.URLError as err:
            raise CliError(EXIT_API, "network_error", str(err.reason)) from err
        text = raw.decode("utf-8", errors="replace")
        try:
            return status, json.loads(text) if text else None
        except json.JSONDecodeError:
            return status, text

    def login(self) -> object:
        email, password = self.creds
        self._save_token(None)
        status, data = self._send("POST", "/auth/login", {"email": email, "password": password})
        if status >= 400 or not isinstance(data, dict) or not data.get("access_token"):
            raise CliError(EXIT_AUTH, "login_failed", "Login rejected; check FOLLOWISH_EMAIL/FOLLOWISH_PASSWORD",
                           status=status, body=data)
        self._save_token(data["access_token"])
        # Keep the bearer token out of stdout: agent transcripts and logs would retain it.
        return {"user": data.get("user")}

    def logout(self) -> object:
        data = self.call("POST", "/auth/logout")
        self._save_token(None)
        return data

    def call(self, method: str, path: str, body: object = None, form: dict | None = None) -> object:
        if not self.token:
            self.login()
        status, data = self._send(method, path, body, form)
        if status == 401:  # session expired: log in again once
            self.login()
            status, data = self._send(method, path, body, form)
        if status >= 400:
            raise CliError(EXIT_API, "api_error", f"{method} {path} returned HTTP {status}", status=status, body=data)
        return data


# ---------------------------------------------------------------- helpers

def iso_to_server_date(value: str | None) -> str | None:
    if value is None or value.lower() == "none":
        return None
    try:
        return dt.date.fromisoformat(value).strftime(SERVER_DATE_FORMAT)
    except ValueError as err:
        raise CliError(EXIT_USAGE, "usage_error", f"Invalid date {value!r}; expected YYYY-MM-DD or 'none'") from err


def server_date(value: object) -> str | None:
    """Normalize a dateEnd from an API response to the DD.MM.YYYY format the API accepts."""
    if not value:
        return None
    text = str(value)
    for parse in (lambda s: dt.date.fromisoformat(s[:10]), lambda s: dt.datetime.strptime(s, SERVER_DATE_FORMAT)):
        try:
            return parse(text).strftime(SERVER_DATE_FORMAT)
        except ValueError:
            continue
    return text


def pick(source: object, fields: tuple[str, ...], nested: str) -> dict:
    """Take known fields from a response that may wrap the entity under `nested`."""
    if isinstance(source, dict) and isinstance(source.get(nested), dict):
        source = source[nested]
    if not isinstance(source, dict):
        raise CliError(EXIT_API, "unexpected_response", f"Cannot read current {nested} to update it", body=source)
    return {key: source[key] for key in fields if key in source}


def wishlist_changes(args: argparse.Namespace) -> dict:
    changes = {
        "name": args.name,
        "comment": args.comment,
        "nameVisibleStatus": args.names,
        "viewPrivacyStatus": args.view,
        "reservePrivacyStatus": args.reserve,
        "isProfileLinkVisible": args.profile_link_visible,
        "allowedFriendIds": args.allowed_friend_ids,
    }
    changes = {key: value for key, value in changes.items() if value is not None}
    if args.date_end is not None:
        changes["dateEnd"] = iso_to_server_date(args.date_end)
    return changes


def present_changes(args: argparse.Namespace) -> dict:
    changes = {
        "name": args.name,
        "price": args.price,
        "currency": args.currency,
        "desireLevel": args.desire,
        "description": args.description,
        "storeLink": args.link,
        "imageLink": args.image_link,
    }
    return {key: value for key, value in changes.items() if value is not None}


def present_form(fields: dict) -> dict:
    # Mirrors the site: optional fields are omitted when empty, protocol-relative links get https.
    form = {key: value for key, value in fields.items() if value not in (None, "")}
    link = str(form.get("storeLink", ""))
    if link.startswith("//"):
        form["storeLink"] = "https:" + link
    return form


# ---------------------------------------------------------------- command handlers

def cmd_login(c: Client, a):  return c.login()
def cmd_logout(c: Client, a): return c.logout()
def cmd_whoami(c: Client, a): return c.call("POST", "/auth/user", {"withoutNewsModals": True})

def cmd_wishlists_list(c: Client, a): return c.call("GET", "/wishlists")
def cmd_wishlists_get(c: Client, a):  return c.call("POST", f"/wishlists/{a.key}", {"isPublicPage": False})
def cmd_wishlists_delete(c: Client, a): return c.call("DELETE", f"/wishlists/{a.key}")


def cmd_wishlists_create(c: Client, a):
    body = {"name": a.name, "comment": "", "dateEnd": None, "nameVisibleStatus": "yesWithNames",
            "viewPrivacyStatus": "all", "reservePrivacyStatus": "all", "isProfileLinkVisible": False,
            "theme": None, "allowedFriendIds": [], "useCase": "editOrCreateWishlistUseCase"}
    body.update(wishlist_changes(a))
    return c.call("POST", "/wishlists", body)


def cmd_wishlists_update(c: Client, a):
    changes = wishlist_changes(a)
    if not changes:
        raise CliError(EXIT_USAGE, "usage_error", "Nothing to update: pass at least one option")
    current = pick(cmd_wishlists_get(c, a), WISHLIST_FIELDS, "wishlist")
    current["dateEnd"] = server_date(current.get("dateEnd"))
    current["comment"] = current.get("comment") or ""
    current.setdefault("allowedFriendIds", [])
    return c.call("PUT", f"/wishlists/{a.key}", {**current, **changes})


def cmd_presents_get(c: Client, a):    return c.call("GET", f"/presents/{a.id}")
def cmd_presents_delete(c: Client, a): return c.call("DELETE", f"/presents/{a.id}")
def cmd_presents_friends(c: Client, a): return c.call("GET", "/presents/all/forFriends")
def cmd_presents_unreserve(c: Client, a): return c.call("PUT", f"/presents/{a.id}/cancelReserve")
def cmd_presents_done(c: Client, a):
    return c.call("POST", f"/presents/{a.id}/setWishExecuted", {"isWishExecuted": not a.undo})
def cmd_presents_move(c: Client, a):
    return c.call("POST", f"/presents/{a.id}/transferPresent", {"wishlistLinkKey": a.to})


def cmd_presents_add(c: Client, a):
    fields = {"currency": "RUB", "desireLevel": 0, **present_changes(a)}
    return c.call("POST", f"/wishlists/{a.key}/presents", form=present_form(fields))


def cmd_presents_update(c: Client, a):
    changes = present_changes(a)
    if not changes:
        raise CliError(EXIT_USAGE, "usage_error", "Nothing to update: pass at least one option")
    fetched = cmd_presents_get(c, a)
    current = pick(fetched, PRESENT_FIELDS, "present")
    # The API returns the picture as `image` but accepts it back as `imageLink`; without it the image is dropped.
    current.setdefault("imageLink", fetched.get("image"))
    return c.call("POST", f"/presents/{a.id}", form=present_form({**current, **changes}))


def cmd_friends_list(c: Client, a):   return c.call("GET", "/friends")
def cmd_friends_add(c: Client, a):    return c.call("POST", "/friends/sendFriendRequest", {"friendUserLink": a.user_link})
def cmd_friends_remove(c: Client, a): return c.call("POST", "/friends/removeFriend", {"friendId": a.friend_id})

def cmd_profile_get(c: Client, a):       return c.call("GET", f"/profile/{a.user_link}")
def cmd_profile_wishlists(c: Client, a): return c.call("GET", f"/profile/{a.user_link}/wishlists")


def cmd_api(c: Client, a):
    try:
        body = json.loads(a.json) if a.json else None
    except json.JSONDecodeError as err:
        raise CliError(EXIT_USAGE, "usage_error", f"--json is not valid JSON: {err}") from err
    path = a.path if a.path.startswith("/") else "/" + a.path
    return c.call(a.method.upper(), path, body)


# ---------------------------------------------------------------- output views
# Default output keeps only what an agent needs; names match the CLI arguments. --raw bypasses all of this.

def day(value: object) -> str | None:
    # The API sends "2026-10-05 00:00:00" or "2000-05-10T00:00:00.000000Z" (midnight UTC), so the date prefix is exact.
    return str(value)[:10] if value else None


def compact(value: object) -> object:
    """Drop null and empty-string fields recursively; an absent field means "not set"."""
    if isinstance(value, dict):
        return {k: compact(v) for k, v in value.items() if v is not None and v != ""}
    if isinstance(value, list):
        return [compact(v) for v in value]
    return value


def wishlist_brief(w: dict) -> dict:
    return {"key": w.get("linkKey"), "name": w.get("name"), "presentsCount": w.get("presentsCount"),
            "dateEnd": day(w.get("dateEnd"))}


def present_brief(p: dict) -> dict:
    return {"id": p.get("id"), "name": p.get("name"), "price": p.get("price"), "currency": p.get("currency"),
            "reserved": p.get("isReserved"), "done": p.get("isWishExecuted")}


def present_full(p: dict) -> dict:
    return {**present_brief(p), "description": p.get("description"), "link": p.get("storeLink"),
            "image": p.get("image"), "desire": p.get("desireLevel")}


def wishlist_full(w: dict) -> dict:
    return {"key": w.get("linkKey"), "name": w.get("name"), "dateEnd": day(w.get("dateEnd")),
            "comment": w.get("comment"), "view": w.get("viewPrivacyStatus"), "reserve": w.get("reservePrivacyStatus"),
            "names": w.get("nameVisibleStatus"), "presents": [present_brief(p) for p in w.get("presents") or []]}


def user_view(u: dict) -> dict:
    u = u.get("user", u)  # auth login wraps the user, auth whoami does not
    return {"id": u.get("id"), "name": u.get("name"), "email": u.get("email"), "userLink": u.get("userLink"),
            "isPremium": u.get("isPremium")}


def reserved_view(presents: list) -> list:
    views = []
    for p in presents:
        wishlist = p.get("wishlist") or {}
        owner = wishlist.get("user") or {}
        views.append({"id": p.get("id"), "name": p.get("name"), "price": p.get("price"), "currency": p.get("currency"),
                      "link": p.get("storeLink"), "owner": owner.get("name"),
                      "wishlist": {"key": wishlist.get("linkKey"), "name": wishlist.get("name")}})
    return views


def friends_view(data: dict) -> dict:
    def request(r: dict, side: str) -> dict:
        # Friend requests carry the other user as `toUser`/`fromUser` with id and name only, no profile link.
        other = r.get(side) or {}
        return {"userId": other.get("id"), "name": other.get("name")}

    return {"friends": [{"id": f.get("id"), "userLink": f.get("userLink"), "name": f.get("name"),
                         "birthday": day(f.get("birthday"))} for f in data.get("friends") or []],
            "incoming": [request(r, "fromUser") for r in data.get("incomingFriendRequests") or []],
            "outgoing": [request(r, "toUser") for r in data.get("outgoingFriendRequests") or []]}


def profile_view(p: dict) -> dict:
    return {"userLink": p.get("userLink"), "name": p.get("name"), "description": p.get("description"),
            "birthday": day(p.get("birthday")), "isFriend": (p.get("friendship") or {}).get("isFriend")}


def ok(**fields: object):
    """View for mutations: confirm and echo the identifiers from the command line."""
    return lambda data, a: {"ok": True, **{k: getattr(a, attr) for k, attr in fields.items()}}


HELP_WISHLISTS = "followish wishlists --help — all wishlist commands"
HELP_PRESENTS = "followish presents --help — all present commands"
HELP_FRIENDS = "followish friends --help — all friend commands"
HINTS_WISHLIST_KEY = (
    "followish wishlists get KEY — settings and presents of a wishlist",
    "followish presents add KEY --name ... — add a present",
    "followish wishlists update KEY ... | delete KEY",
    HELP_WISHLISTS,
)
HINTS_PRESENT_ID = (
    "followish presents get ID — full present: description, link, image",
    "followish presents update ID ... | done ID | move ID --to KEY | delete ID",
    HELP_PRESENTS,
)


# ---------------------------------------------------------------- argument parsing

def id_from_url(value: str, markers: tuple[str, ...], what: str) -> str:
    """Accept a bare identifier or a followish.io URL; take the path segment right after one of `markers`."""
    value = value.strip()
    if "/" not in value:
        return value
    url = urllib.parse.urlsplit(value if "://" in value else "https://" + value)
    host = (url.hostname or "").removeprefix("www.")
    if host != "followish.io":
        raise argparse.ArgumentTypeError(f"not a followish.io URL: {value!r}")
    segments = [s for s in url.path.split("/") if s]
    for marker, following in zip(segments, segments[1:]):
        if marker in markers:
            return following
    raise argparse.ArgumentTypeError(
        f"no {what} in {value!r}; expected a URL containing /{'/ or /'.join(markers)}/<{what}>")


HELP_KEY = "wishlist key or URL, e.g. niepglsrgxbuhn or https://followish.io/mywishlist/niepglsrgxbuhn."
HELP_ID = "present id or its followish.io URL (.../presents/ID/...)."
HELP_USER_LINK = "user profile link or URL, e.g. dql4hgh6ccuzkw or https://followish.io/app/users/dql4hgh6ccuzkw."


def wishlist_key(value: str) -> str:
    # Share links are /mywishlist/KEY; the owner's app pages are /app/wishlists/KEY/...
    return id_from_url(value, ("mywishlist", "wishlists"), "wishlist key")


def user_link(value: str) -> str:
    return id_from_url(value, ("users",), "user link")


def present_id(value: str) -> str:
    # Edit pages look like /app/wishlists/KEY/presents/ID/edit.
    found = id_from_url(value, ("presents",), "present id")
    if not found.isdigit():
        raise argparse.ArgumentTypeError(f"present id must be a number, got {found!r}")
    return found


class JsonErrorParser(argparse.ArgumentParser):
    """Report usage errors as JSON so agents can parse them like any other failure."""

    def error(self, message: str) -> None:
        raise CliError(EXIT_USAGE, "usage_error", message, usage=self.format_usage().strip())


def add_wishlist_options(p: argparse.ArgumentParser, name_required: bool) -> None:
    p.add_argument("--name", required=name_required, help="Wishlist title.")
    p.add_argument("--comment", help="Free-text description shown under the title.")
    p.add_argument("--date-end", metavar="YYYY-MM-DD", help="Event date (birthday etc.); 'none' clears it.")
    p.add_argument("--view", choices=["all", "friends", "justMe", "selectedFriends"],
                   help="Who can see the wishlist. Default on create: all.")
    p.add_argument("--reserve", choices=["all", "friends"],
                   help="Who can reserve gifts. Default on create: all.")
    p.add_argument("--names", choices=["yesWithNames", "yesWithoutNames", "no"],
                   help="Whether the owner sees reservations: with names, anonymously, or not at all. "
                        "Default on create: yesWithNames.")
    p.add_argument("--profile-link-visible", action=argparse.BooleanOptionalAction,
                   help="Show a link to the owner's profile on the wishlist page.")
    p.add_argument("--allowed-friend-ids", nargs="*", metavar="FRIEND_ID",
                   help="Friend ids allowed to view when --view selectedFriends.")


def add_present_options(p: argparse.ArgumentParser, name_required: bool) -> None:
    p.add_argument("--name", required=name_required, help="Gift title.")
    p.add_argument("--price", help="Price as a number, e.g. 4990.")
    p.add_argument("--currency", help=f"Currency code. Default on add: RUB. Known: {CURRENCIES}.")
    p.add_argument("--desire", type=int, metavar="LEVEL",
                   help="How much the owner wants it; integer, 0 is the default level.")
    p.add_argument("--description", help="Free-text notes: size, color, model.")
    p.add_argument("--link", help="Store URL of the gift.")
    p.add_argument("--image-link", help="Direct URL of an image for the gift.")


def build_parser() -> argparse.ArgumentParser:
    fmt = argparse.RawDescriptionHelpFormatter
    root = JsonErrorParser(
        prog="followish", formatter_class=fmt,
        description="Followish (followish.io) wishlist service client, designed for AI agents.",
        epilog=(
            "Output: JSON on stdout as {\"result\": ..., \"hints\": [...]}. `result` keeps only the useful\n"
            "fields, named like the CLI arguments (key, id, userLink, link, view...); empty fields are\n"
            "omitted. `hints` lists next commands, with KEY/ID/USER_LINK placeholders taken from `result`.\n"
            "--raw prints the unmodified API response instead (API field names, e.g. linkKey, storeLink);\n"
            "`api` always prints raw.\n"
            "Errors are JSON too: {\"error\": {\"type\", \"message\", ...}} with a non-zero exit code:\n"
            "  1 API or network error, 2 invalid arguments, 3 missing credentials / login rejected.\n\n"
            "Auth: FOLLOWISH_EMAIL and FOLLOWISH_PASSWORD from the environment or ./.env\n"
            "(environment wins). Login is automatic; the access token is cached in\n"
            "~/.cache/followish (override with FOLLOWISH_CACHE_DIR) and renewed on HTTP 401.\n\n"
            "Identifiers: a wishlist is addressed by its key (returned by 'wishlists list'), a present\n"
            "by its numeric id, a user by their profile link. Each also accepts a followish.io URL:\n"
            "https://followish.io/mywishlist/KEY, https://followish.io/app/users/USER_LINK,\n"
            ".../presents/ID/... The identifier is cut out of the URL before the request.\n\n"
            "Start with: followish wishlists list"),
    )
    root.add_argument("--env-file", metavar="PATH", help="Read credentials from this .env file instead of ./.env.")
    root.add_argument("--pretty", action="store_true", help="Indent JSON output for humans.")
    root.add_argument("--raw", action="store_true",
                      help="Print the unmodified API response instead of {result, hints}. Field names differ.")
    groups = root.add_subparsers(dest="group", required=True, metavar="GROUP")

    def command(parent, name: str, handler, help_text: str, description: str | None = None, *,
                view, hints: tuple[str, ...] = ()):
        p = parent.add_parser(name, help=help_text, description=description or help_text, formatter_class=fmt)
        p.set_defaults(handler=handler, view=view, hints=hints)
        return p

    def group(name: str, help_text: str):
        g = groups.add_parser(name, help=help_text, description=help_text)
        return g.add_subparsers(dest="command", required=True, metavar="COMMAND")

    auth = group("auth", "Session management. Login happens automatically; use these to check or reset it.")
    command(auth, "login", cmd_login, "Force a fresh login with the configured credentials.", view=lambda d, a: user_view(d),
            hints=("followish wishlists list — your wishlists",))
    command(auth, "logout", cmd_logout, "End the server session.", view=ok())
    command(auth, "whoami", cmd_whoami, "Show the logged-in user (id, name, email, profile link).",
            view=lambda d, a: user_view(d), hints=("followish wishlists list — your wishlists",))

    wl = group("wishlists", "Your wishlists: list, read, create, edit, delete.")
    command(wl, "list", cmd_wishlists_list, "List your wishlists: key, name, presentsCount, dateEnd.",
            view=lambda d, a: [wishlist_brief(w) for w in d], hints=HINTS_WISHLIST_KEY)
    p = command(wl, "get", cmd_wishlists_get, "Show one wishlist: settings and a short list of its presents.",
                view=lambda d, a: wishlist_full(d), hints=HINTS_PRESENT_ID[:2] + HINTS_WISHLIST_KEY[1:])
    p.add_argument("key", type=wishlist_key, help=HELP_KEY)
    p = command(wl, "create", cmd_wishlists_create, "Create a wishlist.",
                "Create a wishlist. Only --name is required; the rest default to a public list.\n"
                "Example: followish wishlists create --name 'Birthday' --date-end 2026-12-01",
                view=lambda d, a: {"ok": True, **wishlist_brief(d)}, hints=HINTS_WISHLIST_KEY)
    add_wishlist_options(p, name_required=True)
    p = command(wl, "update", cmd_wishlists_update, "Change wishlist settings.",
                "Change only the passed settings; the rest are read from the server and kept.\n"
                "Example: followish wishlists update abc123 --view friends",
                view=ok(key="key"), hints=HINTS_WISHLIST_KEY[:1])
    p.add_argument("key", type=wishlist_key, help=HELP_KEY)
    add_wishlist_options(p, name_required=False)
    p = command(wl, "delete", cmd_wishlists_delete, "Delete a wishlist and its presents. Irreversible.",
                view=ok(key="key"), hints=("followish wishlists list — remaining wishlists",))
    p.add_argument("key", type=wishlist_key, help=HELP_KEY)

    pr = group("presents", "Gifts inside wishlists: add, edit, mark fulfilled, move, delete.")
    p = command(pr, "get", cmd_presents_get, "Show one present in full.",
                view=lambda d, a: present_full(d), hints=HINTS_PRESENT_ID[1:])
    p.add_argument("id", type=present_id, help=HELP_ID)
    p = command(pr, "add", cmd_presents_add, "Add a present to a wishlist.",
                "Add a present to a wishlist. Only --name is required.\n"
                "Example: followish presents add abc123 --name 'Kindle' --price 12990 --link https://...",
                view=lambda d, a: {"ok": True, "id": d.get("id") if isinstance(d, dict) else None, "wishlist": a.key},
                hints=HINTS_PRESENT_ID)
    p.add_argument("key", type=wishlist_key, help="Wishlist to add the present to: " + HELP_KEY)
    add_present_options(p, name_required=True)
    p = command(pr, "update", cmd_presents_update, "Edit a present.",
                "Change only the passed fields; the rest are read from the server and kept.",
                view=ok(id="id"), hints=HINTS_PRESENT_ID[:1])
    p.add_argument("id", type=present_id, help=HELP_ID)
    add_present_options(p, name_required=False)
    p = command(pr, "delete", cmd_presents_delete, "Delete a present. Irreversible.", view=ok(id="id"),
                hints=("followish wishlists get KEY — remaining presents",))
    p.add_argument("id", type=present_id, help=HELP_ID)
    p = command(pr, "done", cmd_presents_done, "Mark a present as a fulfilled wish (or undo with --undo).",
                view=lambda d, a: {"ok": True, "id": a.id, "done": not a.undo}, hints=HINTS_PRESENT_ID[:1])
    p.add_argument("id", type=present_id, help=HELP_ID)
    p.add_argument("--undo", action="store_true", help="Mark as not fulfilled again.")
    p = command(pr, "move", cmd_presents_move, "Move a present to another of your wishlists.",
                view=ok(id="id", wishlist="to"), hints=("followish wishlists get KEY — presents of the target wishlist",))
    p.add_argument("id", type=present_id, help=HELP_ID)
    p.add_argument("--to", required=True, metavar="KEY", type=wishlist_key, help="Target wishlist: " + HELP_KEY)
    command(pr, "friends", cmd_presents_friends, "List presents you reserved for friends.",
            view=lambda d, a: reserved_view(d),
            hints=("followish presents unreserve ID — cancel your reservation", HELP_PRESENTS))
    p = command(pr, "unreserve", cmd_presents_unreserve, "Cancel your reservation of a friend's present.",
                "Cancel your reservation of a friend's present. Reserving is not supported:\n"
                "the site signs reservations with an anti-bot token, do it in the browser.",
                view=ok(id="id"), hints=("followish presents friends — remaining reservations",))
    p.add_argument("id", type=present_id, help=HELP_ID)

    fr = group("friends", "Friend list management.")
    command(fr, "list", cmd_friends_list, "List friends and pending friend requests.", view=lambda d, a: friends_view(d),
            hints=("followish profile wishlists USER_LINK — a friend's wishlists",
                   "followish friends remove ID — remove a friend (id from this list)", HELP_FRIENDS))
    p = command(fr, "add", cmd_friends_add, "Send a friend request.", view=ok(userLink="user_link"),
                hints=("followish friends list — pending requests",))
    p.add_argument("user_link", type=user_link, help=HELP_USER_LINK)
    p = command(fr, "remove", cmd_friends_remove, "Remove a friend.", view=ok(id="friend_id"),
                hints=("followish friends list — remaining friends",))
    p.add_argument("friend_id", help="Friend's user id (from 'friends list').")

    pf = group("profile", "Other users' public profiles.")
    hints_profile = ("followish profile wishlists USER_LINK — wishlists visible to you",
                     "followish friends add USER_LINK — send a friend request")
    p = command(pf, "get", cmd_profile_get, "Show a user's profile.", view=lambda d, a: profile_view(d),
                hints=hints_profile)
    p.add_argument("user_link", type=user_link, help=HELP_USER_LINK)
    p = command(pf, "wishlists", cmd_profile_wishlists, "List wishlists visible to you on a user's profile.",
                view=lambda d, a: [wishlist_brief(w) for w in d],
                hints=("followish wishlists get KEY — presents of that wishlist (works for others' lists too)",))
    p.add_argument("user_link", type=user_link, help=HELP_USER_LINK)

    p = groups.add_parser(
        "api", formatter_class=fmt, help="Call any Followish API endpoint directly (escape hatch).",
        description="Call any endpoint under https://core.followish.io/api with the current session.\n"
                    "Use it for features without a dedicated command (notifications, settings, friend\n"
                    "request accept/reject). The API is private and undocumented; shapes may change.\n"
                    "Example: followish api POST /notifications/getNotificationsPage")
    p.set_defaults(handler=cmd_api, view=None)  # always raw: there is no known shape to project
    p.add_argument("method", choices=["GET", "POST", "PUT", "PATCH", "DELETE", "get", "post", "put", "patch", "delete"],
                   metavar="METHOD", help="HTTP method: GET, POST, PUT, PATCH or DELETE.")
    p.add_argument("path", help="Path after /api, e.g. /friends.")
    p.add_argument("--json", metavar="BODY", help="JSON request body.")
    return root


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    pretty = "--pretty" in (argv if argv is not None else sys.argv[1:])
    try:
        args = build_parser().parse_args(argv)
        data = args.handler(Client(args.env_file), args)
        if not args.raw and args.view is not None:
            data = {"result": compact(args.view(data, args)), "hints": list(args.hints)}
        emit(data, args.pretty)
        return 0
    except CliError as err:
        emit({"error": {"type": err.kind, "message": str(err), **err.extra}}, pretty)
        return err.code


if __name__ == "__main__":
    sys.exit(main())

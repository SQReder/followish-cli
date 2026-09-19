"""End-to-end check of the CLI against the live followish.io account from .env / the environment.

Run explicitly: python e2e.py
Creates two private (justMe) wishlists named with E2E_PREFIX, walks through the commands and deletes
everything in `finally`; leftovers of a crashed run are swept by name at start.
Every CLI call waits a random pause first so the traffic looks like a person, not a bot:
FOLLOWISH_E2E_PAUSE="min-max" seconds, default 3-8.
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time

E2E_PREFIX = "followish-cli e2e"
MISSING_KEY = "e2e-missing-key-0"
PAUSE_MIN, PAUSE_MAX = (float(x) for x in os.environ.get("FOLLOWISH_E2E_PAUSE", "3-8").split("-"))
HERE = os.path.dirname(os.path.abspath(__file__))

failures: list[str] = []


def cli(*args: str) -> tuple[int, dict]:
    time.sleep(random.uniform(PAUSE_MIN, PAUSE_MAX))
    proc = subprocess.run([sys.executable, os.path.join(HERE, "followish.py"), *args],
                          capture_output=True, text=True, encoding="utf-8", cwd=HERE)
    try:
        return proc.returncode, json.loads(proc.stdout)
    except json.JSONDecodeError:
        return proc.returncode, {"unparsable_stdout": proc.stdout[-500:], "stderr": proc.stderr[-1500:]}


def ok(*args: str) -> object:
    """Run a command that must succeed; return its `result`."""
    code, out = cli(*args)
    if code != 0 or "result" not in out:
        raise AssertionError(f"`followish {' '.join(args)}` exited {code}: {json.dumps(out, ensure_ascii=False)[:800]}")
    return out["result"]


def check(name: str, condition: bool, detail: object = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + ("" if condition else f"  -> {detail}"), flush=True)
    if not condition:
        failures.append(name)


def present_ids(key: str) -> list[int]:
    return [p["id"] for p in ok("wishlists", "get", key).get("presents", [])]


def sweep() -> None:
    for wishlist in ok("wishlists", "list"):
        if wishlist["name"].startswith(E2E_PREFIX):
            ok("wishlists", "delete", wishlist["key"])
            print(f"swept  {wishlist['key']} {wishlist['name']!r}", flush=True)


def scenario(created: list[str]) -> None:
    me = ok("auth", "whoami")
    check("whoami returns user", bool(me.get("userLink")), me)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    first = ok("wishlists", "create", "--name", f"{E2E_PREFIX} A {stamp}", "--view", "justMe",
               "--date-end", "2030-01-31", "--comment", "safe to delete")
    created.append(first["key"])
    second = ok("wishlists", "create", "--name", f"{E2E_PREFIX} B {stamp}", "--view", "justMe")
    created.append(second["key"])
    check("create returns key", bool(first.get("key")) and bool(second.get("key")), (first, second))

    a, b = first["key"], second["key"]
    wishlist = ok("wishlists", "get", f"https://followish.io/mywishlist/{a}")
    check("get by URL returns settings", wishlist.get("view") == "justMe" and wishlist.get("dateEnd") == "2030-01-31",
          wishlist)

    added = ok("presents", "add", a, "--name", "e2e gift", "--price", "1990", "--desire", "2",
               "--description", "first", "--link", "//example.com/gift")
    pid = str(added.get("id"))
    check("presents add returns id", pid.isdigit(), added)

    present = ok("presents", "get", pid)
    check("protocol-relative link gets https", present.get("link") == "https://example.com/gift", present)
    check("added fields stored", (present.get("price"), present.get("desire"), present.get("description"))
          == ("1990", 2, "first"), present)

    ok("presents", "update", pid, "--price", "2990", "--description", "second")
    present = ok("presents", "get", pid)
    check("update changes passed fields", (present.get("price"), present.get("description")) == ("2990", "second"),
          present)
    check("update keeps other fields", present.get("link") == "https://example.com/gift" and present.get("desire") == 2,
          present)

    ok("wishlists", "update", a, "--date-end", "none", "--comment", "cleared")
    wishlist = ok("wishlists", "get", a)
    check("wishlist update clears date", "dateEnd" not in wishlist and wishlist.get("comment") == "cleared", wishlist)

    ok("presents", "move", pid, "--to", f"https://followish.io/mywishlist/{b}")
    check("move puts present into target", int(pid) in present_ids(b) and int(pid) not in present_ids(a))

    ok("presents", "done", pid)
    check("done marks fulfilled", ok("presents", "get", pid).get("done") is True)
    # Depending on the account setting the present stays in place or moves to the fulfilled section.
    fulfilled = [p["id"] for p in ok("presents", "fulfilled").get("presents", [])]
    check("fulfilled present is findable", int(pid) in present_ids(b) or int(pid) in fulfilled)
    ok("presents", "done", pid, "--undo")
    check("undo clears fulfilled", ok("presents", "get", pid).get("done") is False)
    check("undo returns present to its wishlist", int(pid) in present_ids(b))

    code, out = cli("wishlists", "get", MISSING_KEY)
    check("unknown key is api_error 404", code == 1 and out.get("error", {}).get("status") == 404, out)
    code, out = cli("wishlists", "get", "https://example.com/mywishlist/x")
    check("foreign URL is usage_error", code == 2 and out.get("error", {}).get("type") == "usage_error", out)

    ok("presents", "delete", pid)
    code, out = cli("presents", "get", pid)
    check("deleted present is gone", code == 1 and out.get("error", {}).get("status") == 404, out)


def main() -> int:
    print(f"pauses {PAUSE_MIN:g}-{PAUSE_MAX:g}s per call; the run takes a few minutes", flush=True)
    created: list[str] = []
    try:
        sweep()
        scenario(created)
    except AssertionError as err:
        check("scenario ran to the end", False, err)
    finally:
        for key in created:
            code, out = cli("wishlists", "delete", key)
            check(f"cleanup {key}", code == 0, out)
    print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'ALL PASSED'}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

"""Checks for identifier parsing. Run: python -m pytest test_followish.py  (or: python test_followish.py)"""
import argparse

import followish

CASES = [
    (followish.wishlist_key, "niepglsrgxbuhn", "niepglsrgxbuhn"),
    (followish.wishlist_key, "https://followish.io/mywishlist/niepglsrgxbuhn", "niepglsrgxbuhn"),
    (followish.wishlist_key, "followish.io/mywishlist/niepglsrgxbuhn/?utm=x#top", "niepglsrgxbuhn"),
    (followish.wishlist_key, "https://www.followish.io/app/wishlists/abc/presents/5/edit", "abc"),
    (followish.user_link, "https://followish.io/app/users/dql4hgh6ccuzkw", "dql4hgh6ccuzkw"),
    (followish.present_id, "https://followish.io/app/wishlists/abc/presents/1037711/edit", "1037711"),
    (followish.present_id, "1037711", "1037711"),
]
REJECTED = [
    (followish.wishlist_key, "https://evil.example/mywishlist/abc"),
    (followish.wishlist_key, "https://followish.io/app/settings"),
    (followish.present_id, "abc"),
]


def test_identifiers_are_cut_out_of_urls():
    for parse, value, expected in CASES:
        assert parse(value) == expected, (value, parse(value))


def test_foreign_or_unrelated_urls_are_rejected():
    for parse, value in REJECTED:
        try:
            parse(value)
        except argparse.ArgumentTypeError:
            continue
        raise AssertionError(f"{value!r} was accepted")


if __name__ == "__main__":
    test_identifiers_are_cut_out_of_urls()
    test_foreign_or_unrelated_urls_are_rejected()
    print("ok")

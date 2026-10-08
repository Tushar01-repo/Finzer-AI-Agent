from __future__ import annotations

from app.mcp_servers.wishlist.repository import (
    add_to_wishlist,
    ensure_wishlist_table,
    get_wishlist,
    get_wishlist_item,
    remove_from_wishlist,
)


TEST_USER_ID = "wishlist_repository_test_user"
TEST_ASSET_TYPE = "MUTUAL_FUND"
TEST_ASSET_ID = "125497"
TEST_ASSET_NAME = "SBI Small Cap Fund - Direct Plan - Growth"


def print_header(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def main() -> None:
    print_header(
        "FINZER - WISHLIST REPOSITORY TEST"
    )

    # ------------------------------------------------------------------
    # 1. Ensure table exists
    # ------------------------------------------------------------------

    print()
    print("[1] ensure_wishlist_table")

    ensure_wishlist_table()

    print("PASS")

    # ------------------------------------------------------------------
    # Cleanup before test
    # ------------------------------------------------------------------

    remove_from_wishlist(
        user_id=TEST_USER_ID,
        asset_type=TEST_ASSET_TYPE,
        asset_id=TEST_ASSET_ID,
    )

    # ------------------------------------------------------------------
    # 2. Initially not present
    # ------------------------------------------------------------------

    print()
    print("[2] get_wishlist_item - initially absent")

    item = get_wishlist_item(
        user_id=TEST_USER_ID,
        asset_type=TEST_ASSET_TYPE,
        asset_id=TEST_ASSET_ID,
    )

    assert item is None

    print("PASS")

    # ------------------------------------------------------------------
    # 3. Add item
    # ------------------------------------------------------------------

    print()
    print("[3] add_to_wishlist")

    item, created = add_to_wishlist(
        user_id=TEST_USER_ID,
        asset_type=TEST_ASSET_TYPE,
        asset_id=TEST_ASSET_ID,
        asset_name=TEST_ASSET_NAME,
        metadata={
            "scheme_code": TEST_ASSET_ID,
            "plan": "DIRECT",
            "option": "GROWTH",
            "source": "mfapi",
        },
    )

    assert created is True

    assert item.user_id == TEST_USER_ID
    assert item.asset_type == TEST_ASSET_TYPE
    assert item.asset_id == TEST_ASSET_ID
    assert item.asset_name == TEST_ASSET_NAME

    assert (
        item.metadata["scheme_code"]
        == TEST_ASSET_ID
    )

    print(
        "wishlist_id:",
        item.wishlist_id,
    )

    print(
        "asset:",
        item.asset_name,
    )

    print(
        "created:",
        created,
    )

    print("PASS")

    # ------------------------------------------------------------------
    # 4. Read exact item
    # ------------------------------------------------------------------

    print()
    print("[4] get_wishlist_item")

    fetched_item = get_wishlist_item(
        user_id=TEST_USER_ID,
        asset_type=TEST_ASSET_TYPE,
        asset_id=TEST_ASSET_ID,
    )

    assert fetched_item is not None

    assert (
        fetched_item.wishlist_id
        == item.wishlist_id
    )

    assert (
        fetched_item.asset_name
        == TEST_ASSET_NAME
    )

    print(
        "Found:",
        fetched_item.asset_name,
    )

    print("PASS")

    # ------------------------------------------------------------------
    # 5. Get complete user wishlist
    # ------------------------------------------------------------------

    print()
    print("[5] get_wishlist")

    wishlist = get_wishlist(
        user_id=TEST_USER_ID,
    )

    assert len(wishlist) == 1

    assert (
        wishlist[0].asset_id
        == TEST_ASSET_ID
    )

    print(
        "Wishlist count:",
        len(wishlist),
    )

    print("PASS")

    # ------------------------------------------------------------------
    # 6. Idempotent add
    # ------------------------------------------------------------------

    print()
    print("[6] duplicate add - idempotency")

    duplicate_item, created = add_to_wishlist(
        user_id=TEST_USER_ID,
        asset_type=TEST_ASSET_TYPE,
        asset_id=TEST_ASSET_ID,
        asset_name=TEST_ASSET_NAME,
        metadata={
            "scheme_code": TEST_ASSET_ID,
            "plan": "DIRECT",
            "option": "GROWTH",
            "source": "mfapi",
        },
    )

    assert created is False

    assert (
        duplicate_item.wishlist_id
        == item.wishlist_id
    )

    wishlist = get_wishlist(
        user_id=TEST_USER_ID,
    )

    assert len(wishlist) == 1

    print(
        "created:",
        created,
    )

    print(
        "Wishlist count:",
        len(wishlist),
    )

    print("PASS")

    # ------------------------------------------------------------------
    # 7. Remove
    # ------------------------------------------------------------------

    print()
    print("[7] remove_from_wishlist")

    removed = remove_from_wishlist(
        user_id=TEST_USER_ID,
        asset_type=TEST_ASSET_TYPE,
        asset_id=TEST_ASSET_ID,
    )

    assert removed is True

    print(
        "removed:",
        removed,
    )

    print("PASS")

    # ------------------------------------------------------------------
    # 8. Verify removed
    # ------------------------------------------------------------------

    print()
    print("[8] verify item removed")

    item_after_delete = get_wishlist_item(
        user_id=TEST_USER_ID,
        asset_type=TEST_ASSET_TYPE,
        asset_id=TEST_ASSET_ID,
    )

    assert item_after_delete is None

    wishlist = get_wishlist(
        user_id=TEST_USER_ID,
    )

    assert len(wishlist) == 0

    print("PASS")

    # ------------------------------------------------------------------
    # 9. Idempotent remove
    # ------------------------------------------------------------------

    print()
    print("[9] duplicate remove - idempotency")

    removed_again = remove_from_wishlist(
        user_id=TEST_USER_ID,
        asset_type=TEST_ASSET_TYPE,
        asset_id=TEST_ASSET_ID,
    )

    assert removed_again is False

    print(
        "removed:",
        removed_again,
    )

    print("PASS")

    # ------------------------------------------------------------------
    # Finished
    # ------------------------------------------------------------------

    print_header(
        "ALL WISHLIST REPOSITORY TESTS PASSED"
    )


if __name__ == "__main__":
    main()
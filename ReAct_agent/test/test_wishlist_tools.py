from __future__ import annotations

from app.mcp_servers.wishlist.tools import (
    add_to_wishlist,
    get_wishlist,
    is_in_wishlist,
    remove_from_wishlist,
)


TEST_USER_ID = "wishlist_tool_test_user"

TEST_ASSET_TYPE = "MUTUAL_FUND"
TEST_ASSET_ID = "125497"
TEST_ASSET_NAME = "SBI Small Cap Fund - Direct Plan - Growth"


def header(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def main() -> None:
    header("FINZER - WISHLIST TOOL TEST")

    # ==============================================================
    # Cleanup
    # ==============================================================

    remove_from_wishlist(
        TEST_USER_ID,
        TEST_ASSET_TYPE,
        TEST_ASSET_ID,
    )

    # ==============================================================
    # 1. Empty wishlist
    # ==============================================================

    print()
    print("[1] get_wishlist - empty")

    response = get_wishlist(
        TEST_USER_ID
    )

    assert response.status == "success"
    assert response.error is None
    assert response.data is not None

    assert response.data.user_id == TEST_USER_ID
    assert response.data.count == 0
    assert response.data.items == []

    print("Count:", response.data.count)
    print("PASS")

    # ==============================================================
    # 2. Check asset not present
    # ==============================================================

    print()
    print("[2] is_in_wishlist - absent")

    response = is_in_wishlist(
        TEST_USER_ID,
        TEST_ASSET_TYPE,
        TEST_ASSET_ID,
    )

    assert response.status == "success"
    assert response.error is None
    assert response.data is not None

    assert response.data.exists is False
    assert response.data.item is None

    print("Exists:", response.data.exists)
    print("PASS")

    # ==============================================================
    # 3. Add asset
    # ==============================================================

    print()
    print("[3] add_to_wishlist")

    response = add_to_wishlist(
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

    assert response.status == "success"
    assert response.error is None
    assert response.data is not None

    assert response.data.created is True

    item = response.data.item

    assert item.user_id == TEST_USER_ID
    assert item.asset_type == TEST_ASSET_TYPE
    assert item.asset_id == TEST_ASSET_ID
    assert item.asset_name == TEST_ASSET_NAME

    wishlist_id = item.wishlist_id

    print("wishlist_id:", wishlist_id)
    print("created:", response.data.created)
    print("asset:", item.asset_name)
    print("PASS")

    # ==============================================================
    # 4. Check asset present
    # ==============================================================

    print()
    print("[4] is_in_wishlist - present")

    response = is_in_wishlist(
        TEST_USER_ID,
        TEST_ASSET_TYPE,
        TEST_ASSET_ID,
    )

    assert response.status == "success"
    assert response.data is not None

    assert response.data.exists is True
    assert response.data.item is not None

    assert (
        response.data.item.wishlist_id
        == wishlist_id
    )

    print("Exists:", response.data.exists)
    print("PASS")

    # ==============================================================
    # 5. Get wishlist
    # ==============================================================

    print()
    print("[5] get_wishlist - populated")

    response = get_wishlist(
        TEST_USER_ID
    )

    assert response.status == "success"
    assert response.data is not None

    assert response.data.count == 1
    assert len(response.data.items) == 1

    assert (
        response.data.items[0].asset_id
        == TEST_ASSET_ID
    )

    print("Count:", response.data.count)
    print(
        "Asset:",
        response.data.items[0].asset_name,
    )

    print("PASS")

    # ==============================================================
    # 6. Duplicate add
    # ==============================================================

    print()
    print("[6] duplicate add - idempotency")

    response = add_to_wishlist(
        user_id=TEST_USER_ID,
        asset_type="mutual_fund",
        asset_id=TEST_ASSET_ID,
        asset_name=TEST_ASSET_NAME,
        metadata={
            "scheme_code": TEST_ASSET_ID,
        },
    )

    assert response.status == "success"
    assert response.data is not None

    assert response.data.created is False

    assert (
        response.data.item.wishlist_id
        == wishlist_id
    )

    print("created:", response.data.created)
    print("PASS")

    # ==============================================================
    # 7. Verify asset_type normalization
    # ==============================================================

    print()
    print("[7] asset_type normalization")

    response = is_in_wishlist(
        TEST_USER_ID,
        "mutual_fund",
        TEST_ASSET_ID,
    )

    assert response.status == "success"
    assert response.data is not None

    assert response.data.exists is True

    assert (
        response.data.asset_type
        == "MUTUAL_FUND"
    )

    print(
        "Normalized asset_type:",
        response.data.asset_type,
    )

    print("PASS")

    # ==============================================================
    # 8. Validation - empty user
    # ==============================================================

    print()
    print("[8] validation - empty user_id")

    response = get_wishlist("")

    assert response.status == "error"
    assert response.data is None
    assert response.error is not None

    assert (
        response.error.type
        == "VALIDATION_ERROR"
    )

    assert response.error.retryable is False

    print(
        "Error type:",
        response.error.type,
    )

    print(
        "Message:",
        response.error.message,
    )

    print("PASS")

    # ==============================================================
    # 9. Validation - empty asset type
    # ==============================================================

    print()
    print("[9] validation - empty asset_type")

    response = is_in_wishlist(
        TEST_USER_ID,
        "",
        TEST_ASSET_ID,
    )

    assert response.status == "error"
    assert response.data is None
    assert response.error is not None

    assert (
        response.error.type
        == "VALIDATION_ERROR"
    )

    print(
        "Error type:",
        response.error.type,
    )

    print("PASS")

    # ==============================================================
    # 10. Validation - empty asset id
    # ==============================================================

    print()
    print("[10] validation - empty asset_id")

    response = is_in_wishlist(
        TEST_USER_ID,
        TEST_ASSET_TYPE,
        "",
    )

    assert response.status == "error"
    assert response.data is None
    assert response.error is not None

    assert (
        response.error.type
        == "VALIDATION_ERROR"
    )

    print(
        "Error type:",
        response.error.type,
    )

    print("PASS")

    # ==============================================================
    # 11. Validation - empty asset name
    # ==============================================================

    print()
    print("[11] validation - empty asset_name")

    response = add_to_wishlist(
        user_id=TEST_USER_ID,
        asset_type=TEST_ASSET_TYPE,
        asset_id="another_asset",
        asset_name="",
    )

    assert response.status == "error"
    assert response.data is None
    assert response.error is not None

    assert (
        response.error.type
        == "VALIDATION_ERROR"
    )

    print(
        "Error type:",
        response.error.type,
    )

    print("PASS")

    # ==============================================================
    # 12. Remove asset
    # ==============================================================

    print()
    print("[12] remove_from_wishlist")

    response = remove_from_wishlist(
        TEST_USER_ID,
        TEST_ASSET_TYPE,
        TEST_ASSET_ID,
    )

    assert response.status == "success"
    assert response.data is not None

    assert response.data.removed is True

    print(
        "removed:",
        response.data.removed,
    )

    print("PASS")

    # ==============================================================
    # 13. Verify removed
    # ==============================================================

    print()
    print("[13] verify removed")

    response = is_in_wishlist(
        TEST_USER_ID,
        TEST_ASSET_TYPE,
        TEST_ASSET_ID,
    )

    assert response.status == "success"
    assert response.data is not None

    assert response.data.exists is False
    assert response.data.item is None

    print(
        "Exists:",
        response.data.exists,
    )

    print("PASS")

    # ==============================================================
    # 14. Duplicate remove
    # ==============================================================

    print()
    print("[14] duplicate remove - idempotency")

    response = remove_from_wishlist(
        TEST_USER_ID,
        TEST_ASSET_TYPE,
        TEST_ASSET_ID,
    )

    assert response.status == "success"
    assert response.data is not None

    assert response.data.removed is False

    print(
        "removed:",
        response.data.removed,
    )

    print("PASS")

    # ==============================================================
    # Final cleanup
    # ==============================================================

    remove_from_wishlist(
        TEST_USER_ID,
        TEST_ASSET_TYPE,
        TEST_ASSET_ID,
    )

    header(
        "ALL WISHLIST TOOL TESTS PASSED"
    )


if __name__ == "__main__":
    main()
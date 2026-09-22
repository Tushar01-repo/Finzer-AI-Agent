import pymupdf


PDF_PATH = "data/documents/raw/HitechFlowSolutionsDAP_p.pdf"

# Zero-based page indexes:
# 6 -> PDF page 7
# 9 -> PDF page 10
PAGES_TO_INSPECT = [6, 9]


doc = pymupdf.open(PDF_PATH)

try:
    for page_index in PAGES_TO_INSPECT:
        page = doc[page_index]

        print()
        print("=" * 80)
        print(f"PAGE {page_index + 1}")
        print("=" * 80)

        data = page.get_text(
            "dict",
            sort=True,
        )

        for block_index, block in enumerate(
            data.get("blocks", [])
        ):
            if block.get("type") != 0:
                continue

            print()
            print(
                f"BLOCK {block_index} "
                f"BBOX={block.get('bbox')}"
            )

            for line_index, line in enumerate(
                block.get("lines", [])
            ):
                spans = line.get(
                    "spans",
                    [],
                )

                text = "".join(
                    span.get("text", "")
                    for span in spans
                ).strip()

                if not text:
                    continue

                print()
                print(
                    f"  LINE {line_index}: "
                    f"{text!r}"
                )

                for span_index, span in enumerate(
                    spans
                ):
                    span_text = span.get(
                        "text",
                        "",
                    ).strip()

                    if not span_text:
                        continue

                    print(
                        "    "
                        f"SPAN {span_index}: "
                        f"text={span_text!r} | "
                        f"size={span.get('size')} | "
                        f"font={span.get('font')} | "
                        f"flags={span.get('flags')} | "
                        f"bbox={span.get('bbox')}"
                    )

finally:
    doc.close()
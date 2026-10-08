# Finzer AI --- Document / IPO Ingestion Pipeline

> **Status:** Work in progress. Discovery, PDF download, parsing, table
> extraction, style profiling, TOC detection, heading detection, and
> hierarchy assignment are implemented and tested on a real SEBI IPO
> document. Chunking, persistence, queues, embeddings, and E2E
> orchestration are next.

## 1. Goal and architecture

The document path is intentionally separate from news ingestion. An IPO
PDF is not one large article: it contains pages, headings, sections,
subsections, paragraphs, tables, and layout information that should be
preserved before chunking.

``` text
SEBI / future NSE / BSE / Company IR
        ↓
Document discovery
        ↓
PDF download + validation
        ↓
PyMuPDF layout parsing
        ↓
Logical block splitting
        ↓
pdfplumber table extraction
        ↓
Style profiling
        ↓
TOC detection
        ↓
Heading / structure detection
        ↓
Hierarchy assignment
        ↓
Section-aware hybrid chunking        [NEXT]
        ↓
PostgreSQL + pgvector                 [PLANNED]
        ↓
RabbitMQ document queues              [PLANNED]
        ↓
Embedding Router                      [PLANNED]
```

**Core principle:** preserve document structure first; chunk and embed
second.

## 2. Current files

``` text
app/document_ingestion/
├── __init__.py
├── models.py
├── downloader.py
├── parser.py
├── table_extractor.py
├── providers/
│   ├── __init__.py
│   ├── base.py
│   └── sebi.py
└── structure/
    ├── __init__.py
    ├── style_profiler.py
    ├── toc_detector.py
    ├── structure_detector.py
    └── hierarchy_assigner.py
```

  Component                               Status
  --------------------------------------- ---------
  Models                                  ✅
  Provider abstraction                    ✅
  SEBI discovery                          ✅
  PDF downloader                          ✅
  PyMuPDF parser                          ✅
  Logical block splitting                 ✅
  pdfplumber tables                       ✅
  Style profiler                          ✅
  TOC detector                            ✅
  Structure detector                      ✅
  Hierarchy assigner                      ✅
  Section-aware chunker                   ⏳ Next
  PostgreSQL document schema/repository   ⏳
  RabbitMQ document queues                ⏳
  Embedding worker                        ⏳
  E2E                                     ⏳

## 3. `models.py` --- intermediate representation

The models form the contract between stages.

-   **`DiscoveredDocument`**: source, raw title, filing URL, PDF URL,
    published date, company/document metadata.
-   **`DownloadedDocument`**: local path, filename, byte size, SHA-256,
    plus the discovery record.
-   **`DocumentElement`**: logical text element with page, type, text,
    bounding box, font information, boldness,
    section/subsection/heading, and metadata.
-   **`ExtractedTable`**: page, rows, bbox, title and hierarchy
    metadata.
-   **`ParsedDocument`**: document plus parsed elements/tables and
    parser metadata.
-   **`DocumentChunk`**: future chunk representation with content type,
    pages, hierarchy, token count, and metadata.

Separating the IR from source-specific scraping means all later stages
can work identically for SEBI, NSE, BSE, or company IR PDFs.

## 4. `providers/base.py` --- provider boundary

`DocumentProvider` defines the discovery interface. Provider-specific
code ends once a `DiscoveredDocument` is produced:

``` text
SEBI ──────┐
NSE ───────┼──→ DiscoveredDocument → shared pipeline
BSE ───────┤
Company IR ┘
```

The parser, downloader, chunker, database code, and embedding worker
should not need SEBI-specific HTML knowledge.

## 5. `providers/sebi.py` --- SEBI discovery

The SEBI provider handles the public-issues listing page, form
parameters, listing-table extraction, AJAX pagination, filing URLs, and
direct PDF URLs.

An important observation from real data is that the **listing type and
actual linked PDF identity can differ**. For example:

``` text
Listing:
Hi-Tech Flow Solutions Limited - DRHP

Direct PDF filename:
HitechFlowSolutionsDAP_p.pdf
```

Therefore the source listing type should be retained separately from the
actual downloadable document identity.

`pdf_url=None` is also valid. Some listings require opening `filing_url`
and discovering one or more PDFs there. A filing-page resolver is a
later enhancement.

## 6. `downloader.py` --- safe PDF acquisition

Download flow:

``` text
HTTP stream
→ temporary file
→ non-empty validation
→ `%PDF-` signature validation
→ SHA-256
→ atomic move
→ DownloadedDocument
```

The signature check prevents an HTML error page from entering the PDF
parser.

Real validated example:

``` text
data/documents/raw/HitechFlowSolutionsDAP_p.pdf
Size: 539312 bytes
SHA256: bda833d7d4de6d69570f633867428cd23c0b19803434c0d07b531066841f5f2f
```

Planned deduplication has two layers:

``` text
before download: SHA256(source + normalized_pdf_url)
after download:  SHA256(file bytes)
```

## 7. `parser.py` --- PyMuPDF structured parsing

The parser uses:

``` python
page.get_text("dict", sort=True)
```

rather than immediately flattening a page with `page.get_text()`.

This preserves evidence needed later:

``` text
blocks
lines
spans
page number
bounding boxes
font names
font sizes
reading order
boldness
```

### Why PyMuPDF blocks were not enough

A real block contained:

``` text
For further details, see ...
4.
Objects of the Offer
```

Another contained:

``` text
body paragraph...
7.
Summary of Key Performance Indicators
```

If physical blocks were trusted blindly, the heading would be swallowed
by the previous paragraph.

The parser therefore performs **conservative logical splitting** inside
physical blocks.

Element counts changed during this work:

``` text
Initial physical representation: 293
After numeric heading splitting: 310
After alphabetic/Roman support: 313
```

The increase is intentional: mixed physical blocks became more accurate
logical elements.

## 8. Structural marker splitting

Supported standalone marker shapes include:

``` text
Numeric:      1.   4.   12.   1)   3.2.
Alphabetic:   a)   b)   c)    A.   B)
Roman:        i)   ii)  iii)  IV.
```

A marker by itself is **not enough**. Financial documents contain many
standalone numbers and letters.

A physical split is made only with strong evidence:

``` text
structural marker
+ following title line
+ marker line strongly bold
+ title line strongly bold
+ title contains letters
+ title is not numeric-heavy
+ title length <= 180
→ logical split
```

Example found in the real PDF:

``` text
Before:
We provide flow solution products...
...
34.96%, driven by capacity expansion.
b)
Industries Served and Typical Customers / Clients

After:
Element 1 = body paragraph
Element 2 = "b)\nIndustries Served and Typical Customers / Clients"
```

Validated output:

``` text
p4_b4_g1 | page=4 | bold=True
'b)\nIndustries Served and Typical Customers / Clients'
```

### Why parser splitting uses a stricter bold threshold

Boldness is character weighted:

``` text
bold_ratio = bold_characters / total_characters
```

Ordinary element-level bold classification uses roughly **50%**.

Parser-level structural splitting requires roughly **80%** for both
marker and title lines.

Reason: splitting changes the intermediate representation itself, so it
should require stronger evidence than a later, reversible heading
classification.

## 9. `table_extractor.py` --- pdfplumber tables

Tables are extracted independently with `pdfplumber`:

``` text
page.find_tables()
→ table.extract()
→ cell cleanup
→ basic shape validation
→ ExtractedTable
```

The tested 17-page document produced **15 table candidates**.

A real financial table contained fields such as:

``` text
Particulars
Fiscal 2026
Fiscal 2025
Fiscal 2024
Amount
% of total revenue from operations
```

We deliberately do **not** delete every text element that overlaps a
table. pdfplumber can identify large layout regions as table candidates,
so aggressive deletion could destroy useful text. For now, raw text and
table representations are both preserved.

## 10. `style_profiler.py` --- document-relative typography

Different issuers use different typography, so fixed rules such as
`font_size >= 14` are unreliable.

The profiler calculates document-level properties including:

``` text
body font size
dominant font
font-size frequencies
font-name frequencies
bold ratio
uppercase count
short-bold count
candidate heading sizes
```

Earlier profiling of the test PDF showed approximately:

``` text
Body font size: 11.04
Dominant font: TimesNewRomanPSMT
Total elements: 293   (before final parser splitting)
Bold elements: 145
Bold ratio: ~0.495
Heading-size candidates: []
```

This was important evidence: **font size provided almost no heading
discrimination**, and nearly half the blocks were bold. Therefore
neither font size nor boldness can be the only heading rule.

## 11. `toc_detector.py` --- document-provided structure

The TOC detector searches early pages for signals such as:

``` text
TABLE OF CONTENTS
CONTENTS
INDEX
```

and attempts to parse title/page entries.

A TOC is valuable because it is structure explicitly supplied by the
document rather than inferred from typography.

The current test PDF returned:

``` text
TOC found: False
Entries: 0
```

That is valid, not a failure. The short abridged-style PDF simply does
not provide a useful TOC, so the pipeline falls back to numbering,
typography, text shape, geometry, and table awareness.

## 12. `structure_detector.py` --- multi-signal heading scoring

The structure detector answers:

> **Does this logical element look like a heading?**

It intentionally does not assign the final hierarchy role.

The current tested scoring scheme is approximately:

  Evidence                                                    Score
  --------------------------------------- -------------------------
  explicit `SECTION` pattern                                     +6
  TOC match                                                      +6
  numbered heading pattern                                       +3
  enumerated heading pattern                                   +2.5
  predominantly bold                                           +1.5
  uppercase                                                   +1.25
  very short text                                             +0.75
  short text                                                  +0.25
  moderately larger font                                         +1
  significantly larger font                                      +2
  long text                                                    -1.5
  numeric-heavy text                                             -4
  repeated placeholder/artifact signals                          -2
  table-row-like text                                            -3
  many short lines                                               -2
  inside detected table                     strong/hard veto (\~-5)

Current heading threshold:

``` text
3.0
```

### Why scoring instead of one rule?

A real section:

``` text
4.
Objects of the Offer
```

gets roughly:

``` text
numbered pattern    +3.00
bold                +1.50
very short          +0.75
-------------------------
total                5.25
```

A real subsection:

``` text
b)
Industries Served and Typical Customers / Clients
```

gets roughly:

``` text
enumerated pattern  +2.50
bold                +1.50
very short          +0.75
-------------------------
total                4.75
```

A table header such as:

``` text
Fiscal 2026
```

may also be bold and short, but table geometry provides strong negative
evidence. This is why combining independent signals is more robust than
relying on one style rule.

## 13. Table-aware heading protection

During testing, table cells such as:

``` text
Particulars
Fiscal 2026
Fiscal 2025
Fiscal 2024
Amount
% of
total revenue
```

were bold and could otherwise resemble headings.

The detector checks element coordinates against table bounding boxes.
Elements inside a detected table receive a strong veto.

Observed example:

``` text
'Particulars'
inside_table=True
score=-5.0
```

This successfully kept financial table headers out of the section
hierarchy.

A future refinement may make the veto quality-aware because some
pdfplumber table boxes can be overly broad.

## 14. Why numeric-heavy/table-row penalties exist

IPO documents contain huge amounts of:

``` text
₹4,171.71 million
34.96%
2026
2025
2024
```

Such content may be short and bold. Numeric-density and table-row-like
penalties stop financial values from becoming headings merely because of
typography.

## 15. Real heading-detection result

After parser improvements:

``` text
Elements: 313
Tables: 15
TOC: False
Heading candidates: 22
```

Recovered structure:

``` text
1. Summary of the primary business
   a) Business Overview - Products and Services
   b) Industries Served and Typical Customers / Clients
   c) Segment Reporting and Revenue Contribution
   d) Key Geographies Served
   e) Revenue Concentration among Top 5 Customers
   f) Key Manufacturing or Other Facilities
   g) Business Strengths and Strategies

2. Summary of the industry
3. Promoters
4. Objects of the Offer
5. Pre-Offer and Post-Offer shareholding...
6. Summary of Restated Financial Information
7. Summary of Key Performance Indicators
8. Risk Factors
9. Details of weighted average cost...
10. Board of Directors and Key Managerial Personnel
11. Auditor Qualifications
12. Summary of outstanding litigation
```

Representative scores:

``` text
1. Summary of the primary business              5.25
a) Business Overview - Products and Services    4.75
b) Industries Served...                         4.75
4. Objects of the Offer                         5.25
7. Summary of Key Performance Indicators        5.25
8. Risk Factors                                 5.25
```

## 16. Known visual-heading false positives

The detector also identified front-matter labels such as:

``` text
ON
CLOSES ON
```

and:

``` text
INVESTOR BID/
OFFER PERIOD
```

They scored approximately:

``` text
bold          +1.50
uppercase     +1.25
very short    +0.75
-------------------
total          3.50
```

Another candidate was:

``` text
IN THE NATURE OF ABRIDGED PROSPECTUS -
MEMORANDUM CONTAINING SALIENT FEATURES...
```

around the threshold.

We deliberately avoided hardcoded exclusions such as:

``` python
if text == "INVESTOR BID/OFFER PERIOD":
    return False
```

because such fixes would overfit one issuer.

Instead, the next layer distinguishes **visual heading candidates** from
**real hierarchy roles**.

## 17. `hierarchy_assigner.py` --- structural role

The hierarchy assigner answers:

``` text
StructureDetector:
Does it look like a heading?

HierarchyAssigner:
What structural role does that heading play?
```

Roles include:

``` text
SECTION
SUBSECTION
HEADING
UNSTRUCTURED
```

Examples:

``` text
1. Summary of the primary business
→ SECTION

b) Industries Served and Typical Customers / Clients
→ SUBSECTION

INVESTOR BID/OFFER PERIOD
→ UNSTRUCTURED
```

Unstructured visual headings **do not reset hierarchy state**.

## 18. Hierarchy state machine

Conceptually:

``` python
current_section = None
current_subsection = None
current_heading = None
```

After:

``` text
1. Summary of the primary business
```

state becomes:

``` text
section = "1. Summary of the primary business"
subsection = None
heading = None
```

After:

``` text
a) Business Overview
```

state becomes:

``` text
section = "1. Summary of the primary business"
subsection = "a) Business Overview"
heading = None
```

Following paragraphs inherit that context.

When:

``` text
2. Summary of the industry
```

appears, lower levels reset:

``` text
section = "2. Summary of the industry"
subsection = None
heading = None
```

This reset prevents content in section 2 from incorrectly inheriting
subsection `g)` from section 1.

## 19. Tested hierarchy result

The current test produced the desired behavior:

``` text
ON / CLOSES ON
→ unstructured
→ section=None
→ subsection=None

INVESTOR BID / OFFER PERIOD
→ unstructured
→ section=None
→ subsection=None

IN THE NATURE OF ABRIDGED PROSPECTUS...
→ unstructured
→ section=None
→ subsection=None
```

Then:

``` text
1. Summary of the primary business
→ section

a) Business Overview
→ subsection under section 1

b) Industries Served
→ subsection under section 1

...
g) Business Strengths and Strategies
→ subsection under section 1
```

Then:

``` text
2. Summary of the industry
→ new section
→ subsection reset to None
```

Sections 3 through 12 were also recognized as top-level sections.

## 20. Original text vs normalized hierarchy text

The parser preserves the physical representation:

``` text
4.
Objects of the Offer
```

while hierarchy metadata can store:

``` text
4. Objects of the Offer
```

The original `element.text` is not overwritten.

This gives us both:

``` text
source-faithful extracted text
+
clean retrieval metadata
```

which helps debugging, source display, future highlighting, and
retrieval.

## 21. Physical structure vs semantic classification

These are intentionally separate concerns.

Physical structure answers:

``` text
Where are the sections?
What is nested under what?
```

A later optional semantic classifier can map original headings to
canonical Finzer categories:

``` text
"8. Risk Factors"
→ RISK_FACTORS

"6. Summary of Restated Financial Information"
→ FINANCIALS

"1. Summary of the primary business"
→ BUSINESS
```

The canonical category should never replace the original heading.

Future example:

``` json
{
  "section": "8. Risk Factors",
  "canonical_section": "RISK_FACTORS"
}
```

## 22. Why not ask an LLM to classify every block?

An LLM could classify every paragraph as heading/body, but doing so
would be:

``` text
more expensive
slower
non-deterministic
harder to debug
unnecessary for obvious layout structure
```

Most structure is already encoded in:

``` text
numbering
font
boldness
coordinates
layout
TOC
text shape
```

Preferred strategy:

``` text
deterministic layout + TOC + rules
        ↓
optional semantic mapping
        ↓
LLM fallback only for genuinely ambiguous cases
```

## 23. Current real-world validation document

Test document:

``` text
data/documents/raw/HitechFlowSolutionsDAP_p.pdf
```

Current observed result:

``` text
Pages: 17
Logical elements: 313
Table candidates: 15
TOC detected: False
Heading candidates: 22
```

This document exposed several useful edge cases:

``` text
paragraph + heading merged into one physical block
alphabetic subsection merged with body text
same-size headings and body
many bold table cells
front-matter labels that resemble headings
financial numeric-heavy content
no usable TOC
```

Those real failures directly drove the current design.

## 24. Known limitations

**Text spacing:** PDF extraction can produce strings such as
`TypicalCustomers`, `RevenueContribution`, or `-Products`. We currently
avoid aggressive repair heuristics.

**Heading continuation:** some headings can appear truncated due to
layout extraction. More documents should be tested before introducing
continuation rules.

**Table over-detection:** pdfplumber can return overly broad table
regions. A future table-quality score may consider page coverage,
row/column counts, density, numeric density, and header consistency.

**TOC coverage:** the current short document has no usable TOC. Full
DRHP/RHP documents still need validation.

**Scanned PDFs:** OCR is not implemented as a default path. Intended
behavior is native text first, with OCR only as a fallback for pages
that genuinely lack a meaningful text layer.

## 25. Next stage --- section-aware hybrid chunking

The next file is `chunker.py`.

The chunker should consume the structured intermediate representation,
not raw PDF text.

Target:

``` text
SECTION
  ↓
SUBSECTION
  ↓
paragraphs
  ↓
chunk within the same structural context
```

Example future chunk:

``` json
{
  "content_type": "TEXT",
  "content": "...",
  "section": "1. Summary of the primary business",
  "subsection": "b) Industries Served and Typical Customers / Clients",
  "heading": null,
  "page_start": 4,
  "page_end": 4,
  "token_count": 742
}
```

Tentative text-chunk target:

``` text
600–1000 tokens
80–150 token overlap
```

These values should ultimately be validated through retrieval evaluation
rather than treated as permanent constants.

## 26. Planned table chunking

Tables should remain structurally distinct.

``` text
ExtractedTable
→ normalize rows/columns
→ attach section/subsection context
→ convert to retrieval-friendly representation
→ split large tables by rows
```

Large table chunks should repeat column headers.

A Markdown-like representation is preferable to embedding raw internal
JSON:

``` text
Section: 6. Summary of Restated Financial Information

| Particulars | Fiscal 2026 | Fiscal 2025 | Fiscal 2024 |
|-------------|-------------|-------------|-------------|
| Revenue     | ...         | ...         | ...         |
```

## 27. Planned persistence

The existing news tables remain separate.

Proposed document model:

``` text
documents
-----------------------------
document_id
document_key
company_name
document_type
source_url
file_name
published_at
status
metadata
created_at
updated_at
```

``` text
document_chunks
-----------------------------
chunk_id
document_id
chunk_index
content_type
section
subsection
heading
page_start
page_end
content
token_count
metadata
created_at
```

``` text
document_chunk_embeddings
-----------------------------
embedding_id
chunk_id
provider
model
dimension
embedding VECTOR(1024)
created_at
```

Keeping embeddings separate allows re-embedding without
reparsing/rechunking the original document.

## 28. Planned RabbitMQ and embedding path

Reuse the existing broker/vhost but use document-specific queues:

``` text
document.processing
document.processing.retry.1
document.processing.retry.2
document.processing.retry.3
document.processing.dlq

document.embedding
document.embedding.retry.1
document.embedding.retry.2
document.embedding.retry.3
document.embedding.dlq
```

RabbitMQ is intentionally deferred until PDF → structure → hierarchy →
chunking is reliable. There is no benefit in distributing incorrect
chunks faster.

Planned embedding path:

``` text
document chunk
→ document.embedding
→ embedding worker
→ existing Embedding Router
   ├── Bedrock
   └── OpenAI fallback
→ 1024-dimensional vector
→ pgvector
```

Do not mix incompatible embedding spaces inside the same searchable
index without an explicit migration/design.

## 29. Development philosophy

The implementation has intentionally progressed one layer at a time:

``` text
Discovery
→ Download
→ Parse
→ Inspect real failures
→ Improve logical splitting
→ Extract tables
→ Profile typography
→ Detect TOC
→ Score headings
→ Inspect false positives
→ Assign hierarchy
→ Validate on real PDF
→ Chunk
```

This avoids compounding errors:

``` text
bad parser
→ bad headings
→ bad hierarchy
→ bad chunks
→ bad embeddings
→ poor retrieval
```

Fixing structure before persistence and embeddings keeps failures
observable and debuggable.

## 30. Current milestone summary

Implemented and validated:

``` text
Source-independent models                    ✅
Provider architecture                        ✅
SEBI discovery                               ✅
Validated PDF downloading                    ✅
SHA-256 file identity                        ✅
PyMuPDF structured parsing                   ✅
Logical physical-block splitting             ✅
Numeric/alphabetic/Roman markers             ✅
Character-weighted bold detection            ✅
pdfplumber table extraction                  ✅
Document-relative typography profiling       ✅
TOC detection with fallback                  ✅
Multi-signal heading scoring                 ✅
Table-aware heading suppression              ✅
Numeric/table-row false-positive penalties   ✅
Section/subsection hierarchy assignment      ✅
Front-matter isolated as unstructured        ✅
Original extracted heading text preserved    ✅
```

Next milestone:

``` text
section-aware hybrid chunking
→ persistence
→ RabbitMQ
→ embedding worker
→ pgvector
→ E2E retrieval validation
```

> **Final design principle:** do not reduce financial PDFs to plain text
> too early. Preserve pages, layout, tables, headings, and hierarchy
> first; use that structure to create retrieval-quality chunks
> afterward.

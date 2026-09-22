Yes. I went through the SEBI scraper you shared. The important part is that you already solved several SEBI-specific quirks: the listing comes from the `sid=3, ssid=15, smid=10` page, pagination uses the AJAX endpoint and `nextValue`, and the listing parser handles SEBI's missing `<tbody>` and nested PDF anchors.  

I would **keep this logic**, but refactor it into our document-ingestion architecture rather than keeping it as one large scraper script.

## Proposed SEBI → document pipeline

```text
SEBI Public Issues
        │
        ▼
SEBIDiscoveryProvider
        │
        │ AJAX pagination
        │
        ▼
DiscoveredDocument
        │
        ├── date
        ├── company/document name
        ├── filing_url
        ├── pdf_url
        └── source = SEBI
        │
        ▼
Document Deduplication
        │
        ├── already processed → skip
        │
        └── new
              │
              ▼
        PDF Downloader
              │
              ▼
        Raw PDF storage
              │
              ▼
          PDF Parser
        ┌─────┴─────┐
        │           │
       TEXT       TABLES
        │           │
        ▼           ▼
     PyMuPDF     pdfplumber
        │           │
        └─────┬─────┘
              ▼
       Structure Detector
              │
        ┌─────┼────────┐
        │     │        │
     section subsection heading
        │
        ▼
      Chunker
        │
        ├── TEXT chunks
        └── TABLE chunks
              │
              ▼
         PostgreSQL
              │
              ▼
      document.embedding
              │
              ▼
       Embedding Router
              │
              ▼
         VECTOR(1024)
```

### 1. Separate SEBI discovery from PDF processing

Right now your script does:

```python
extract_records(...)
...
download_pdf(...)
```

inside the same scraping loop. 

I want to separate those responsibilities.

We'll create:

```text
app/
└── document_ingestion/
    ├── providers/
    │   ├── __init__.py
    │   ├── base.py
    │   └── sebi.py
    │
    ├── downloader.py
    ├── parser.py
    ├── table_extractor.py
    │
    ├── structure/
    │   ├── style_profiler.py
    │   ├── toc_detector.py
    │   └── structure_detector.py
    │
    ├── chunker.py
    ├── models.py
    └── service.py
```

That `providers/` layer is important because **SEBI is only one source**.

Later:

```text
providers/
├── sebi.py
├── nse.py
├── bse.py
└── company_ir.py
```

can all produce the same internal object.

---

## 2. `sebi.py` will contain your existing SEBI-specific logic

The current script already discovers the correct form dynamically and preserves the required SEBI parameters such as `nextValue`, `sid`, `ssid`, `smid`, dates, search fields, etc. 

That belongs inside:

```text
providers/sebi.py
```

Conceptually:

```python
class SEBIDocumentProvider:

    def discover(self, start_page=1, end_page=None):
        ...
        return list[DiscoveredDocument]
```

It should **not download or parse PDFs**.

It only discovers:

```python
DiscoveredDocument(
    source="sebi",
    published_date="...",
    title="M K C AGRO FRESH LIMITED - DRHP",
    filing_url="...",
    pdf_url="..."
)
```

Your existing extraction is already producing essentially these four fields: `date`, `name`, `filing_url`, and `pdf_url`. 

---

## 3. We should parse the SEBI title

This is one place I'd improve your current code.

SEBI gives something like:

```text
M K C AGRO FRESH LIMITED - DRHP
```

We should preserve the original title:

```text
title =
"M K C AGRO FRESH LIMITED - DRHP"
```

but also derive:

```text
company_name =
"M K C AGRO FRESH LIMITED"

document_type =
"DRHP"
```

Similarly:

```text
ABC LIMITED - RHP
ABC LIMITED - DRHP
ABC LIMITED - Prospectus
ABC LIMITED - Addendum
ABC LIMITED - Draft Abridged Prospectus
```

becomes normalized metadata.

But we **never throw away the original SEBI name**.

---

## 4. Important: don't download before deduplication

This is one change I'd definitely make.

Your current code checks whether the filename already exists:

```python
if os.path.exists(file_path):
    return True
```

before downloading. 

That's useful, but for our ingestion service it isn't strong enough.

Instead:

```text
SEBI record
    ↓
generate document_key
    ↓
PostgreSQL lookup
    ↓
┌───────────────────────────────┐
│ already known?               │
│                               │
│ YES → skip                    │
│ NO  → download                │
└───────────────────────────────┘
```

For example:

```text
document_key =
SHA256(source + normalized_pdf_url)
```

and after download we can additionally calculate:

```text
file_sha256
```

This protects us against both duplicate listing records and identical PDFs appearing under different URLs.

---

## 5. Downloader becomes source-independent

Your existing `download_pdf()` correctly streams the response in chunks and sanitizes the filename.  

We'll move the generic parts to:

```text
document_ingestion/downloader.py
```

Then:

```text
SEBI provider
     ↓
pdf_url
     ↓
PDFDownloader
```

The downloader shouldn't know anything about SEBI.

I would also add validation:

```text
HTTP 200
    ↓
Content-Type / PDF signature
    ↓
starts with %PDF-
    ↓
calculate SHA256
    ↓
save
```

So an HTML error/challenge page doesn't accidentally become:

```text
something.pdf
```

---

## 6. Store the SEBI metadata before parsing

Suppose SEBI gives:

```text
Date:
17 Sep 2026

Name:
XYZ LIMITED - DRHP

Filing:
https://sebi...

PDF:
https://sebi...xyz.pdf
```

First create:

```text
documents
─────────────────────────────────────
document_id
document_key

source                sebi
source_title          XYZ LIMITED - DRHP
company_name          XYZ LIMITED
document_type         DRHP

filing_url
pdf_url

published_at

file_name
file_path
file_sha256

page_count

status
error_message

metadata JSONB

created_at
updated_at
```

That means even if parsing fails, we still know:

> We discovered this filing from SEBI, attempted it, and parsing failed.

That's much better operationally than losing failed PDFs.

---

## 7. Then PDF processing begins

Once downloaded:

```text
PDF
 │
 ├──────────────────────────┐
 │                          │
 ▼                          ▼
PyMuPDF                 pdfplumber
 │                          │
 ▼                          ▼
Text/layout              Tables
 │                          │
 │                          │
 └────────────┬─────────────┘
              ▼
      Structure processing
```

I would actually parse **text/layout first**, then use tables as a second extraction channel.

---

## 8. Structure detection happens per PDF

This connects to your previous question about every company having different headings.

```text
PDF
 ↓
PyMuPDF blocks
 ↓
style_profiler.py
 ↓
discover dominant body style
 ↓
discover probable heading styles
 ↓
toc_detector.py
 ↓
extract TOC candidates
 ↓
structure_detector.py
 ↓
construct hierarchy
```

For example:

```text
XYZ Ltd DRHP

16pt bold
"SECTION V – ABOUT OUR COMPANY"
        ↓
SECTION

13pt bold
"OUR BUSINESS"
        ↓
SUBSECTION

11pt bold
"Manufacturing Facilities"
        ↓
HEADING

9pt normal
"We currently operate..."
        ↓
BODY
```

Another company's PDF can use completely different font sizes. The style profiler adapts to that document.

---

## 9. Tables are extracted separately but inserted into the hierarchy

Suppose page 214 looks like:

```text
RESTATED FINANCIAL INFORMATION

The following table sets forth...

--------------------------------
Particulars | FY24 | FY25 | FY26
Revenue     | ...
PAT         | ...
--------------------------------

Notes:
...
```

We don't want:

```text
text chunk
table chunk
text chunk
```

with no relationship.

We want:

```text
Section
FINANCIAL INFORMATION

    Text block
    "The following table sets forth..."

    Table
    "Particulars | FY24..."

    Text block
    "Notes..."
```

Therefore each extracted object gets coordinates:

```json
{
  "page": 214,
  "bbox": [x0, y0, x1, y1]
}
```

This allows us to reconstruct the reading order.

---

## 10. One intermediate representation is critical

Before chunking, I want an intermediate document representation.

Something conceptually like:

```python
DocumentElement
```

with:

```text
element_id
page_number

type:
    heading
    paragraph
    table

text

bbox

font_size
font_name
is_bold

section
subsection
heading

metadata
```

Then a page might internally look like:

```text
Page 214

[HEADING]
RESTATED FINANCIAL INFORMATION

[PARAGRAPH]
The following table sets forth...

[TABLE]
| Particulars | FY24 | FY25 | FY26 |
| Revenue ... |

[PARAGRAPH]
Notes:
1. Revenue from operations...
```

**Chunking operates on this representation, not directly on raw PDF text.**

That's going to make our implementation much cleaner.

---

# Final structure I recommend before coding

I'd slightly refine our earlier structure to this:

```text
app/
└── document_ingestion/
    │
    ├── __init__.py
    │
    ├── models.py
    │
    ├── service.py
    │
    ├── downloader.py
    │
    ├── parser.py
    │
    ├── table_extractor.py
    │
    ├── chunker.py
    │
    ├── providers/
    │   ├── __init__.py
    │   ├── base.py
    │   └── sebi.py
    │
    └── structure/
        ├── __init__.py
        ├── style_profiler.py
        ├── toc_detector.py
        ├── structure_detector.py
        └── section_classifier.py       # later
```

And the responsibility boundaries are:

```text
sebi.py
  SEBI → discovered document metadata

downloader.py
  URL → validated local PDF

parser.py
  PDF → text/layout elements

table_extractor.py
  PDF → structured table elements

style_profiler.py
  elements → understand this PDF's styles

toc_detector.py
  elements → probable document hierarchy

structure_detector.py
  elements + styles + TOC
       → section/subsection/heading hierarchy

chunker.py
  structured elements
       → text/table chunks

service.py
  orchestrates everything
```

The main architectural rule I'd follow is **SEBI-specific code stops at discovery**. Everything after obtaining `pdf_url` should be source-independent. That way, when you later ingest an IPO PDF from NSE/BSE or upload one manually, **the entire PDF → structure → table → chunk → embedding pipeline remains unchanged**.

For file-by-file implementation, I would now start with **`models.py`**, not the SQL migration I suggested earlier. Now that we've seen your SEBI discovery format, defining `DiscoveredDocument`, `ParsedDocument`, `DocumentElement`, `ExtractedTable`, and `DocumentChunk` first will give every subsequent file a stable contract.








##################################################

models.py                    ✅
providers/base.py            ✅
providers/sebi.py            ✅
downloader.py                ✅
parser.py                    ✅
table_extractor.py           ✅
style_profiler.py            ✅
toc_detector.py              ✅
structure_detector.py        ✅ heading candidate detection
hierarchy assignment         ← NEXT
chunker.py
PostgreSQL migration
document_repository.py
service.py
RabbitMQ
embedding worker
E2E
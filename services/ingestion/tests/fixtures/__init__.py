"""Test fixtures for the ingestion pipeline.

Includes:

- ``build_minimal_epub`` — synthesize a valid minimal EPUB byte blob
  for the EPUB extractor tests.
- ``ARXIV_ATOM_FEED`` — recorded Atom XML for the arXiv extractor's
  parse path (no live arXiv in CI).
- ``HTML_SUBSTACK_LIKE`` / ``HTML_PAYWALLED`` — recorded HTML byte
  blobs for the HTML extractor.
- ``MINIMAL_PDF_BYTES`` — a hand-crafted minimal PDF blob for the
  PDF extractor smoke test.

Per the sprint M9 acceptance: fixtures are checked in so CI never
hits live HTTP. The fetcher's HTTP layer is exercised via
``httpx.MockTransport`` handlers in the actual e2e tests.
"""

from __future__ import annotations

import io
import zipfile

# ---------------------------------------------------------------------------
# arXiv Atom — recorded response for id 2402.03300
# ---------------------------------------------------------------------------


ARXIV_ATOM_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2402.03300v2</id>
    <updated>2024-02-15T12:00:00Z</updated>
    <published>2024-02-05T09:15:33Z</published>
    <title>DeepSeekMath: Pushing the Limits of Mathematical Reasoning</title>
    <summary>This is the recorded abstract for the arXiv extractor
    fixture. It spans multiple lines and verifies that the Atom
    parser collapses whitespace and routes through the new fetcher's
    cache + throttle layers.</summary>
    <author><name>Zhihong Shao</name></author>
    <author><name>Peiyi Wang</name></author>
    <category term="cs.CL"/>
    <category term="cs.AI"/>
    <arxiv:primary_category term="cs.CL"/>
  </entry>
</feed>
"""


# ---------------------------------------------------------------------------
# HTML samples
# ---------------------------------------------------------------------------


# Substack-style: clean article body, plenty of words.
HTML_SUBSTACK_LIKE = (b"""<!DOCTYPE html>
<html>
<head>
  <title>The Composable Substrate</title>
  <meta property="og:title" content="The Composable Substrate" />
  <meta name="author" content="Faisal" />
  <meta property="article:published_time" content="2026-05-20T10:00:00Z" />
</head>
<body>
  <nav>site nav</nav>
  <article>
    <h1>The Composable Substrate</h1>
    <p>This is a Substack-style article body. The reader-mode
    extractor should pull this paragraph cleanly along with the
    title and the author byline.</p>
    <p>A second paragraph adds another fifty or so words. The chunker
    will eat this whole article as a single chunk because the total
    token count fits well under the 2000-token default chunk size.
    Knowledge graph nodes will mint from each chunk via the existing
    substrate ops, no special path for HTML content.</p>
    <p>A third paragraph keeps the word count comfortably above the
    50-word floor that the pipeline uses to decide whether to write
    graph rows for the extracted document.</p>
  </article>
  <footer>site footer</footer>
</body>
</html>
""")


HTML_PAYWALLED = (b"""<!DOCTYPE html>
<html>
<head>
  <title>An Important Story</title>
  <meta name="author" content="WSJ Staff" />
</head>
<body>
  <article>
    <h1>An Important Story</h1>
    <p>The first paragraph teases the article.</p>
    <div>Subscribe to continue reading. Sign in to read the full
    story.</div>
  </article>
</body>
</html>
""")


# ---------------------------------------------------------------------------
# Minimal EPUB — synthesized programmatically
# ---------------------------------------------------------------------------


_MIMETYPE = "application/epub+zip"
_CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0"
           xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf"
              media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

_CONTENT_OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:language>en</dc:language>
    <dc:date>2024-01-01</dc:date>
    <dc:identifier id="bookid">fixture-001</dc:identifier>
  </metadata>
  <manifest>
    <item id="chap1" href="chap1.xhtml" media-type="application/xhtml+xml"/>
    <item id="chap2" href="chap2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chap1"/>
    <itemref idref="chap2"/>
  </spine>
</package>
"""

_CHAP_XHTML = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{title}</title></head>
<body>
  <h1>{title}</h1>
  <p>{body}</p>
</body>
</html>
"""


def build_minimal_epub(
    *,
    title: str = "Test Book",
    author: str = "Test Author",
    chapter_words: int = 300,
) -> bytes:
    """Build a valid minimal EPUB byte blob with two chapters.

    Returns bytes suitable for ``zipfile.ZipFile(io.BytesIO(b))``."""
    chap1_body = " ".join(f"alpha-{i}" for i in range(chapter_words))
    chap2_body = " ".join(f"beta-{i}" for i in range(chapter_words // 2))

    buf = io.BytesIO()
    # EPUB requires mimetype to be the FIRST file and stored
    # uncompressed. zipfile honors this when we explicitly use
    # ZIP_STORED for that one entry.
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype: STORED, no extra fields.
        zi = zipfile.ZipInfo("mimetype")
        zi.compress_type = zipfile.ZIP_STORED
        zf.writestr(zi, _MIMETYPE)
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr(
            "OEBPS/content.opf",
            _CONTENT_OPF.format(title=title, author=author),
        )
        zf.writestr(
            "OEBPS/chap1.xhtml",
            _CHAP_XHTML.format(title="Chapter One", body=chap1_body),
        )
        zf.writestr(
            "OEBPS/chap2.xhtml",
            _CHAP_XHTML.format(title="Chapter Two", body=chap2_body),
        )
    return buf.getvalue()


def build_minimal_epub_one_chapter() -> bytes:
    """Even smaller — single chapter, used to test the deterministic
    pagination on a tiny corpus."""
    return build_minimal_epub(
        title="Tiny Book", author="Test", chapter_words=50,
    )


# ---------------------------------------------------------------------------
# Minimal PDF — a hand-crafted single-page text PDF.
# ---------------------------------------------------------------------------


MINIMAL_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
    b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
    b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    b"5 0 obj\n<< /Length 88 >>\nstream\n"
    b"BT /F1 12 Tf 72 720 Td "
    b"(Universal library ingestion test fixture page one body text.) Tj "
    b"ET\nendstream\nendobj\n"
    b"xref\n0 6\n"
    b"0000000000 65535 f \n"
    b"0000000010 00000 n \n"
    b"0000000058 00000 n \n"
    b"0000000115 00000 n \n"
    b"0000000219 00000 n \n"
    b"0000000284 00000 n \n"
    b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n412\n%%EOF\n"
)

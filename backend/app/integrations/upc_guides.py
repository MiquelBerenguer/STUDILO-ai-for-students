"""UPC course guides (guies docents): public PDFs → a course's syllabus (docs/research/UPC_INTEGRATION.md §2.8).

Deterministic: download the public PDF for a subject code, extract the CONTINGUTS / CONTENIDOS / CONTENTS
section with PyMuPDF. Only upc.edu is ever contacted (fixed URL pattern, redirects must stay on upc.edu).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

GUIDE_URL = "https://www.upc.edu/content/grau/guiadocent/pdf/{lang}/{code}"
LANGS = ("ca", "cat", "es", "en")  # both "ca" and "cat" appear in UPC links
MAX_BYTES = 10_000_000
_START = {"CONTINGUTS", "CONTENIDOS", "CONTENTS"}
_END = {"ACTIVITATS", "ACTIVIDADES", "ACTIVITIES", "SISTEMA DE QUALIFICACIÓ", "SISTEMA DE CALIFICACIÓN",
        "GRADING SYSTEM", "BIBLIOGRAFIA", "BIBLIOGRAFÍA", "BIBLIOGRAPHY", "NORMES DE REALITZACIÓ DE LES PROVES.",
        "RECURSOS", "RESOURCES"}
_NOISE = re.compile(
    r"^(Data: \d|(Pàgina|Página|Page):?\s*\d|Dedicació:|Dedicación:|Hours:|Full-or-part-time:|"
    r"(Descripció|Descripción|Description):?$|"
    r"[^:]{2,40}:\s*\d+(?:[.,]\d+)?\s*h$)",  # per-unit workload lines: "Grup gran/Teoria: 6h", "Aprenentatge autònom: 35h"
    re.I)


class GuideError(Exception):
    """User-facing reason a guide couldn't be read."""


@dataclass
class Guide:
    code: str
    title: str
    syllabus: str
    url: str


async def _http_get(url: str) -> bytes | None:
    """GET a upc.edu URL; None on 404. Redirects are followed only within upc.edu."""
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        for _ in range(4):
            host = urlparse(url).hostname or ""
            if not (host == "upc.edu" or host.endswith(".upc.edu")):
                raise GuideError("The course guide link left upc.edu; not following it.")
            resp = await client.get(url)
            if resp.is_redirect and resp.headers.get("location"):
                url = str(resp.url.join(resp.headers["location"]))
                continue
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                raise GuideError(f"upc.edu answered HTTP {resp.status_code}.")
            if len(resp.content) > MAX_BYTES:
                raise GuideError("The course guide is unexpectedly large.")
            return resp.content
    raise GuideError("Too many redirects.")


def parse_guide(pdf: bytes, code: str) -> tuple[str, str]:
    """(title, syllabus) from a guide PDF."""
    import pymupdf

    if not pdf.startswith(b"%PDF"):
        raise GuideError("That subject code didn't return a course guide PDF.")
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    try:
        lines = [ln.strip() for page in doc for ln in page.get_text().splitlines()]
    finally:
        doc.close()
    title = ""
    for i, ln in enumerate(lines):
        if m := re.match(rf"^{re.escape(code)}\s*-\s*(.+)$", ln):
            title = m.group(1)
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if nxt and not re.match(r"^(Unitat|Unidad|Responsible|Coordinating|Última|Last)", nxt):
                title = f"{title} {nxt}"
            break
    start = next((i for i, ln in enumerate(lines) if ln.upper() in _START), None)
    if start is None:
        raise GuideError("I couldn't find the contents section in that course guide.")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].upper() in _END), len(lines))
    body = [ln for ln in lines[start + 1:end] if ln and not _NOISE.match(ln)]
    syllabus = "\n".join(body).strip()
    if len(syllabus) < 20:
        raise GuideError("The contents section of that course guide is empty.")
    return re.sub(r"\s+", " ", title).strip(), syllabus[:20000]


async def fetch_guide(code: str) -> Guide:
    code = code.strip()
    if not re.fullmatch(r"\d{5,6}", code):
        raise GuideError("A UPC subject code is 5–6 digits (e.g. 300021). You'll find it in the timetable or Atenea.")
    for lang in LANGS:
        url = GUIDE_URL.format(lang=lang, code=code)
        pdf = await _http_get(url)
        if pdf:
            title, syllabus = parse_guide(pdf, code)
            return Guide(code=code, title=title, syllabus=syllabus, url=url)
    raise GuideError(f"No public course guide found for {code}.")

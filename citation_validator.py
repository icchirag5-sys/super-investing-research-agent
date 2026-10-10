"""Post-generation checks on a research brief. Pure Python, no model involved.

The model is asked to follow citation rules; this module VERIFIES that it did.

Checks (error = must fix, warning = review):
  errors:   missing section, citation to an unknown source/chunk, uncited numeric claim,
            number that is not in the cited text (unless marked 'derived'), quote that is not in the
            cited text, buy/sell language, promotional claims stated without attribution,
            company claims resting on a wrong-entity source
  warnings: long brief, uncited sentences without numbers, stale source cited without a date cue,
            chunk-less (document-level) citations
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from document_loader import Document
from evidence_extractor import Analysis

CITE_BRACKET = re.compile(r"\[(S\d+(?:\.\d+)?(?:\s*[,;]\s*S\d+(?:\.\d+)?)*)\]")
CITE_ID = re.compile(r"S(\d+)(?:\.(\d+))?")
NUMBER = re.compile(r"\d[\d,]*\.?\d*")
QUOTE = re.compile(r"[\"“]([^\"”]{12,})[\"”]")

REQUIRED_SECTIONS = ["Snapshot", "Bull case", "Bear case", "Open questions"]
RECOMMENDATION = re.compile(
    r"\b(you should (buy|sell|hold|avoid)|we recommend|i recommend|recommend(s|ed)? (buying|selling|holding)|"
    r"price target of|target price of|fair value of|worth ₹|is a (strong )?(buy|sell))\b", re.I)
PROMO_CLAIM = re.compile(r"strong buy|60%\s*upside|consensus (is|was) positive|multibagger", re.I)
HEDGE_WORDS = re.compile(r"\b(claim|claims|claimed|unverified|promotional|blog|alleg|not verified|"
                         r"cannot be verified|hype|tip|should not be relied)", re.I)
DISAMBIGUATION = re.compile(r"\b(different|unrelated|not the same|excluded|appears to be|another (company|entity)|"
                            r"similar name|not about)\b", re.I)
DATE_CUE = re.compile(r"\b(20\d\d|older|stale|outdated|earlier|dated|ago|at the time)\b", re.I)


@dataclass
class Issue:
    severity: str          # "error" | "warning"
    code: str
    message: str
    excerpt: str = ""

    def __str__(self) -> str:
        ex = f' -> "{self.excerpt[:110]}"' if self.excerpt else ""
        return f"[{self.severity.upper()}] {self.code}: {self.message}{ex}"


# ----------------------------------------------------------------------- helpers
def extract_citations(text: str) -> list[tuple[str, str | None]]:
    """All (doc_id, chunk_id|None) pairs cited in `text`, in order."""
    out = []
    for m in CITE_BRACKET.finditer(text):
        for dm in CITE_ID.finditer(m.group(1)):
            doc = f"S{dm.group(1)}"
            out.append((doc, f"{doc}.{dm.group(2)}" if dm.group(2) else None))
    return out


def strip_citations(text: str) -> str:
    return CITE_BRACKET.sub("", text)


PERIOD_LABEL = re.compile(r"\bFY\s?\d{2,4}(?:-\d{2})?\b|\bQ[1-4]\b|\bH[12]\b", re.I)


def _numbers(text: str) -> set[float]:
    vals = set()
    for m in NUMBER.finditer(PERIOD_LABEL.sub(" ", text)):
        raw = m.group(0).rstrip(".,").replace(",", "")
        try:
            vals.add(float(raw))
        except ValueError:
            pass
    return vals


def _norm(s: str) -> str:
    s = re.sub(r"[*_`]", "", s)
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("“", '"').replace("”", '"')).strip().lower()


def split_sections(brief: str) -> dict[str, str]:
    """Map section title -> body, using '## ' headings."""
    sections: dict[str, str] = {}
    current = None
    for line in brief.splitlines():
        m = re.match(r"^#{2,3}\s*(?:\d+\.\s*)?(.+?)\s*$", line)
        if m:
            current = m.group(1)
            sections[current] = ""
        elif current is not None:
            sections[current] += line + "\n"
    return sections


_ABBREV = re.compile(r"\b(Mr|Mrs|Ms|Dr|Rs|No|St|vs|approx)\.|\b(e\.g|i\.e)\.", re.I)


def claim_units(section_body: str) -> list[str]:
    """Bullets and sentences: the granularity at which we require citations.

    A citation placed after a sentence's full stop ("... fell. [S2.2]") stays with that sentence,
    and common abbreviations ("Mr.", "e.g.") do not end a sentence.
    """
    units: list[str] = []
    for para in re.split(r"\n\s*\n|\n(?=\s*[-*•]\s)", section_body):
        para = para.strip()
        if not para:
            continue
        para = re.sub(r"^\s*[-*•]\s+", "", para).replace("\n", " ")
        para = _ABBREV.sub(lambda m: m.group(0).replace(".", "\u2024"), para)     # protect abbreviation dots
        for sent in re.split(r"(?<=[.!?\]])\s+(?=[A-Z*₹])", para):
            sent = sent.replace("\u2024", ".").strip()
            if sent:
                units.append(sent)
    return units


def _cited_text(cites: list[tuple[str, str | None]], docs: dict[str, Document]) -> str:
    parts = []
    for doc_id, chunk_id in cites:
        d = docs.get(doc_id)
        if not d:
            continue
        if chunk_id:
            c = d.chunk_by_id(chunk_id)
            if c:
                # the model is shown title + publication date for every source, so those are citable too
                parts.append(f"{d.source} {d.published.isoformat()} {d.published.strftime('%d %B %Y')}\n"
                             f"{c.section}\n{c.text}")
        else:
            parts.append(d.body)
    return "\n".join(parts)


# ----------------------------------------------------------------------- main validator
def validate_brief(brief: str, docs: list[Document], analysis: Analysis | None = None,
                   require_sources_section: bool = False, max_words: int = 650) -> list[Issue]:
    issues: list[Issue] = []
    by_id = {d.doc_id: d for d in docs}
    flags = {d.doc_id: d.flags for d in docs}
    sections = split_sections(brief)
    allowed_extra: set[float] = set()
    if analysis:
        allowed_extra = {float(analysis.reference_date.day), float(analysis.reference_date.year)}

    # --- structure
    titles = " | ".join(sections)
    for need in REQUIRED_SECTIONS + (["Sources"] if require_sources_section else []):
        if need.lower() not in titles.lower():
            issues.append(Issue("error", "MISSING_SECTION", f"required section '{need}' not found"))

    # --- every citation must resolve
    for doc_id, chunk_id in extract_citations(brief):
        if doc_id not in by_id:
            issues.append(Issue("error", "UNKNOWN_SOURCE", f"cites {doc_id}, which is not in the research pack"))
        elif chunk_id and by_id[doc_id].chunk_by_id(chunk_id) is None:
            issues.append(Issue("error", "UNKNOWN_CHUNK", f"cites {chunk_id}, which does not exist"))

    # --- per-claim checks (skip the Sources section: it is generated, not claimed)
    body_sections = {t: b for t, b in sections.items() if not t.lower().startswith("source")}
    word_count = 0
    for title, body in body_sections.items():
        is_open_q = "open question" in title.lower()
        for unit in claim_units(body):
            word_count += len(strip_citations(unit).split())
            cites = extract_citations(unit)
            plain = strip_citations(unit)
            nums = {n for n in _numbers(plain) if n >= 10 or n != int(n)}   # ignore 1-9 ("two", Q1, etc.)
            derived = bool(re.search(r"\bderived|calculated|computed\b", plain, re.I))

            if RECOMMENDATION.search(plain):
                issues.append(Issue("error", "RECOMMENDATION", "buy/sell/target-price language", unit))

            cited_ids = {c[0] for c in cites}
            if PROMO_CLAIM.search(plain):
                promo_cited = any(any("PROMOTIONAL" in f for f in flags.get(i, [])) for i in cited_ids)
                if not (promo_cited and HEDGE_WORDS.search(plain)):
                    issues.append(Issue("error", "PROMO_CLAIM_UNATTRIBUTED",
                                        "promotional claim stated without attribution to the unverified source", unit))

            if not cites:
                if nums:
                    sev = "warning" if is_open_q else "error"
                    issues.append(Issue(sev, "UNCITED_NUMBER", "numeric statement without a citation", unit))
                elif len(plain.split()) > 8 and not is_open_q and not re.match(r"^\s*\*?(Unknown|Our read)", plain):
                    issues.append(Issue("warning", "UNCITED_SENTENCE", "sentence has no citation", unit))
                continue

            cited_blob = _cited_text(cites, by_id)
            if nums and not derived:
                missing = sorted(n for n in nums if n not in _numbers(cited_blob) and n not in allowed_extra)
                if missing:
                    shown = ", ".join(f"{m:g}" for m in missing)
                    issues.append(Issue("error", "NUMBER_NOT_IN_CITED_SOURCE",
                                        f"number(s) {shown} not found in the cited chunk(s)", unit))
            for q in QUOTE.findall(plain):
                if _norm(q) not in _norm(cited_blob):
                    issues.append(Issue("error", "QUOTE_NOT_IN_SOURCE", "quoted text not found in cited chunk(s)", q))
            for doc_id, chunk_id in cites:
                if chunk_id is None:
                    issues.append(Issue("warning", "DOC_LEVEL_CITATION", f"{doc_id} cited without a chunk ID", unit))
                f = flags.get(doc_id, [])
                if any(x.startswith("ENTITY_MISMATCH") for x in f):
                    if not is_open_q:
                        issues.append(Issue("error", "WRONG_ENTITY_AS_EVIDENCE",
                                            f"{doc_id} appears to be about a different company", unit))
                    elif not DISAMBIGUATION.search(plain):
                        issues.append(Issue("warning", "WRONG_ENTITY_UNEXPLAINED",
                                            f"{doc_id} cited without saying it is a different entity", unit))
                if any(x.startswith("STALE") for x in f) and not DATE_CUE.search(plain):
                    issues.append(Issue("warning", "STALE_SOURCE_NO_DATE", f"{doc_id} is old; give its date", unit))
                if by_id.get(doc_id) and analysis and by_id[doc_id].published > analysis.reference_date:
                    issues.append(Issue("error", "AFTER_REFERENCE_DATE", f"{doc_id} postdates the reference date", unit))

    if word_count > max_words:
        issues.append(Issue("warning", "TOO_LONG", f"~{word_count} words; target is about one page (~500)"))
    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)


# ----------------------------------------------------------------------- sources section
def build_sources_section(brief_body: str, docs: list[Document]) -> str:
    """Generate '## 5. Sources' from the citations actually used. Titles/URLs/dates come from the files,
    never from the model, so they cannot be fabricated."""
    cited: dict[str, list[str]] = {}
    for doc_id, chunk_id in extract_citations(brief_body):
        cited.setdefault(doc_id, [])
        if chunk_id and chunk_id not in cited[doc_id]:
            cited[doc_id].append(chunk_id)
    by_id = {d.doc_id: d for d in docs}

    def order(i: str) -> int:
        return int(i[1:])

    lines = ["## 5. Sources", ""]
    for doc_id in sorted(cited, key=order):
        d = by_id.get(doc_id)
        if not d:
            continue
        locs = []
        for cid in sorted(cited[doc_id], key=lambda c: int(c.split(".")[1])):
            ch = d.chunk_by_id(cid)
            if ch:
                locs.append(f"{cid} ({ch.section})")
        loc_txt = "; ".join(locs) if locs else "document-level"
        lines.append(f"- **[{doc_id}]** {d.source}. {d.url}. Published {d.published.isoformat()}. "
                     f"File: `{d.filename}`. Type: {d.doc_type}. Cited at: {loc_txt}.")
    not_cited = [d for d in docs if d.doc_id not in cited]
    if not_cited:
        lines += ["", "*Reviewed but not relied on:* " + "; ".join(
            f"[{d.doc_id}] {d.source} ({d.published.isoformat()})" for d in not_cited) + "."]
    return "\n".join(lines)

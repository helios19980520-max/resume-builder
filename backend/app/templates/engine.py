"""
DOCX template fill engine.

Strategy: every template is an ordinary .docx that already looks exactly the way we
want. Instead of generating a document from scratch (which would lose fonts, colours,
numbering, indents, tab stops ...), we:

  1. open the original template,
  2. keep a deep copy of one "prototype" paragraph for every role we need
     (title, contact line, section heading, summary, skill line, company line, bullet ...),
  3. wipe the body (keeping the final <w:sectPr> which carries page size + margins),
  4. re-append clones of the prototypes in the order the template dictates, with new text.

Text inside a clone is written as a list of *segments*: (text, fmt) where fmt is a
set of flags among {"b", "i", "u"} or the special tokens TAB / BR. For every segment we
look for a run in the prototype whose formatting matches the requested flags and clone
that run's <w:rPr>; if none exists we clone the first run's rPr and toggle <w:b>/<w:i>.

The result is a paragraph whose pPr, numbering, indents and run properties are
byte-for-byte the template's own.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Iterable

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

TAB = "\t"
BR = "\n"

Segment = tuple[str, object]  # (text, flags-string subset of "biuh"  OR  a ready <w:rPr> element)


@dataclass
class Para:
    role: str
    segments: list[Segment] = field(default_factory=list)

    @staticmethod
    def plain(role: str, text: str) -> "Para":
        return Para(role, [(text, "")])


def md_segments(text: str, base: str = "") -> list[Segment]:
    """Turn '**bold** normal *italic*' markdown into segments."""
    out: list[Segment] = []
    pos = 0
    for m in re.finditer(r"\*\*(.+?)\*\*|(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", text):
        if m.start() > pos:
            out.append((text[pos:m.start()], base))
        if m.group(1) is not None:
            out.append((m.group(1), base + "b"))
        else:
            out.append((m.group(2), base + "i"))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], base))
    return out or [("", base)]


def strip_md(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*|\*(.+?)\*", lambda m: m.group(1) or m.group(2), text)


# --------------------------------------------------------------------------- run helpers
def _run_flags(run) -> str:
    rpr = run.find(qn("w:rPr"))
    flags = ""
    if rpr is None:
        return flags

    def on(tag: str) -> bool:
        el = rpr.find(qn(tag))
        if el is None:
            # rStyle Strong counts as bold
            if tag == "w:b":
                st = rpr.find(qn("w:rStyle"))
                return st is not None and st.get(qn("w:val")) == "Strong"
            return False
        v = el.get(qn("w:val"))
        return v not in ("0", "false", "off")

    if on("w:b"):
        flags += "b"
    if on("w:i"):
        flags += "i"
    if on("w:u"):
        flags += "u"
    st = rpr.find(qn("w:rStyle"))
    if st is not None and st.get(qn("w:val")) == "Hyperlink":
        flags += "h"
    return flags


_RPR_ORDER = ["w:rStyle", "w:rFonts", "w:b", "w:bCs", "w:i", "w:iCs", "w:caps", "w:smallCaps", "w:strike",
              "w:dstrike", "w:outline", "w:shadow", "w:emboss", "w:imprint", "w:noProof", "w:snapToGrid",
              "w:vanish", "w:webHidden", "w:color", "w:spacing", "w:w", "w:kern", "w:position", "w:sz",
              "w:szCs", "w:highlight", "w:u", "w:effect", "w:bdr", "w:shd", "w:fitText", "w:vertAlign",
              "w:rtl", "w:cs", "w:em", "w:lang", "w:eastAsianLayout", "w:specVanish", "w:oMath"]
_RPR_INDEX = {qn(t): i for i, t in enumerate(_RPR_ORDER)}


def _insert_in_order(rpr, el):
    """Insert a child into <w:rPr> at its schema position (Word is picky about rPr order)."""
    my = _RPR_INDEX.get(el.tag, 999)
    for i, child in enumerate(rpr):
        if _RPR_INDEX.get(child.tag, 999) > my:
            rpr.insert(i, el)
            return
    rpr.append(el)


def _set_flag(rpr, tag: str, want: bool):
    el = rpr.find(qn(tag))
    if want:
        if el is None:
            el = OxmlElement(tag)
            _insert_in_order(rpr, el)
        else:
            for k in list(el.attrib):
                del el.attrib[k]
        if tag == "w:u":
            el.set(qn("w:val"), "single")
    else:
        if el is not None:
            rpr.remove(el)
        if tag == "w:b":
            st = rpr.find(qn("w:rStyle"))
            if st is not None and st.get(qn("w:val")) == "Strong":
                rpr.remove(st)


def _text_runs(p) -> list:
    """Runs of the prototype that carry visible text (used as rPr donors)."""
    runs = []
    for r in p.iter(qn("w:r")):
        if r.find(qn("w:t")) is not None and "".join(t.text or "" for t in r.findall(qn("w:t"))).strip():
            runs.append(r)
    if not runs:
        runs = list(p.iter(qn("w:r")))
    return runs


def _donor_rpr(proto_runs: list, flags: str):
    """Pick the rPr of the prototype run whose flags match best, then force flags."""
    want = set(flags)
    best = None
    best_score = -99
    for r in proto_runs:
        have = set(_run_flags(r))
        score = -len(want ^ have) * 10 + (5 if have == want else 0)
        if score > best_score:
            best, best_score = r, score
    rpr = None
    if best is not None:
        rpr = best.find(qn("w:rPr"))
    rpr = copy.deepcopy(rpr) if rpr is not None else OxmlElement("w:rPr")
    have = set(_run_flags(best)) if best is not None else set()
    if (have - {"h"}) != (want - {"h"}):
        _set_flag(rpr, "w:b", "b" in want)
        _set_flag(rpr, "w:i", "i" in want)
        _set_flag(rpr, "w:u", "u" in want)
    return rpr


def _make_run(rpr, text: str):
    r = OxmlElement("w:r")
    if rpr is not None:
        r.append(copy.deepcopy(rpr))
    if text == TAB:
        r.append(OxmlElement("w:tab"))
    elif text == BR:
        r.append(OxmlElement("w:br"))
    else:
        t = OxmlElement("w:t")
        t.text = text
        t.set(qn("xml:space"), "preserve")
        r.append(t)
    return r


def donor_rpr_by_text(proto, needle: str, fallback_flags: str = ""):
    """rPr of the prototype run whose text contains `needle` (case-insensitive); flags-based fallback."""
    runs = _text_runs(proto)
    n = (needle or "").strip().lower()
    if n:
        for r in runs:
            t = "".join(x.text or "" for x in r.findall(qn("w:t"))).lower()
            if n in t or (len(n) > 8 and n[:8] in t):
                rpr = r.find(qn("w:rPr"))
                return copy.deepcopy(rpr) if rpr is not None else OxmlElement("w:rPr")
        # the needle may be split over several runs: use the run holding its first word
        first = n.split()[0] if n.split() else n
        for r in runs:
            t = "".join(x.text or "" for x in r.findall(qn("w:t"))).lower()
            if first and first in t:
                rpr = r.find(qn("w:rPr"))
                return copy.deepcopy(rpr) if rpr is not None else OxmlElement("w:rPr")
    return _donor_rpr(runs, fallback_flags)


def _build_runs(proto, segments: Iterable[Segment]) -> list:
    """Segments -> list of <w:r>. A segment's fmt is either a flags string or a ready <w:rPr> element."""
    proto_runs = _text_runs(proto)
    out = []
    for text, fmt in segments:
        if text == "":
            continue
        rpr = copy.deepcopy(fmt) if not isinstance(fmt, str) else _donor_rpr(proto_runs, fmt)
        for part in re.split(r"(\t|\n)", text):
            if part == "":
                continue
            out.append(_make_run(rpr, TAB if part == "\t" else BR if part == "\n" else part))
    return out


_KEEP_TAGS = (qn("w:drawing"), qn("w:pict"), qn("w:object"))
_MC_ALT = "{http://schemas.openxmlformats.org/markup-compatibility/2006}AlternateContent"


def _is_graphic_run(child) -> bool:
    """A run/element that carries a drawing, shape or picture (kept verbatim when rewriting text)."""
    if child.tag == _MC_ALT:
        return True
    if child.tag != qn("w:r"):
        return False
    return any(child.find(".//" + t) is not None for t in _KEEP_TAGS) or child.find(".//" + _MC_ALT) is not None


def _strip_text_children(p) -> int:
    """Remove text runs/bookmarks etc. from p, keep pPr and graphic runs. Returns insert position for new runs."""
    insert_at = None
    for child in list(p):
        if child.tag == qn("w:pPr") or _is_graphic_run(child):
            continue
        if insert_at is None:
            insert_at = list(p).index(child)
        p.remove(child)
    if insert_at is None:
        insert_at = 1 if p.find(qn("w:pPr")) is not None else 0
    return insert_at


def rewrite_inplace(p, segments: Iterable[Segment]):
    """Replace the text runs of an existing paragraph (e.g. inside a text box) keeping pPr and graphics."""
    runs = _build_runs(p, list(segments))
    at = _strip_text_children(p)
    for k, r in enumerate(runs):
        p.insert(at + k, r)
    return p


def fill_paragraph(proto, segments: Iterable[Segment]):
    """Clone `proto` (<w:p>) and rewrite its content from segments."""
    p = copy.deepcopy(proto)
    runs = _build_runs(proto, list(segments))
    at = _strip_text_children(p)
    for k, r in enumerate(runs):
        p.insert(at + k, r)
    return p


# --------------------------------------------------------------------------- document
class TemplateDoc:
    """Opens a template and exposes prototype paragraphs + a rebuild API."""

    def __init__(self, path: str):
        self.doc = Document(path)
        self.body = self.doc.element.body
        self.paragraphs = [p._p for p in self.doc.paragraphs]
        self.protos: dict[str, object] = {}

    def register(self, role: str, index: int):
        self.protos[role] = copy.deepcopy(self.paragraphs[index])

    def text_of(self, index: int) -> str:
        return "".join(t.text or "" for t in self.paragraphs[index].iter(qn("w:t")))

    def clear_body(self, keep_first_n: int = 0):
        """Remove body content except the trailing sectPr (and optionally first N blocks)."""
        kept = 0
        for child in list(self.body):
            if child.tag == qn("w:sectPr"):
                continue
            if kept < keep_first_n:
                kept += 1
                continue
            self.body.remove(child)

    def append(self, para: Para):
        proto = self.protos[para.role]
        p = fill_paragraph(proto, para.segments)
        sect = self.body.find(qn("w:sectPr"))
        if sect is not None:
            sect.addprevious(p)
        else:
            self.body.append(p)
        return p

    def replace_textbox_paragraph_texts(self, mapping: list[str]):
        """
        For templates whose header is a text box (Daniel): rewrite the i-th paragraph
        inside every <w:txbxContent> (both the DrawingML choice and the VML fallback),
        keeping the first text run's formatting and dropping the rest. Entries set to
        None are left untouched.
        """
        for txbx in self.body.iter(qn("w:txbxContent")):
            paras = txbx.findall(qn("w:p"))
            for i, new in enumerate(mapping):
                if new is None or i >= len(paras):
                    continue
                p = paras[i]
                runs = [r for r in p.findall(qn("w:r")) if r.find(qn("w:t")) is not None]
                if not runs:
                    continue
                # tuple => "replace only the last text run, keep decorative runs before it"
                keep = runs[-1] if isinstance(new, tuple) else runs[0]
                if not isinstance(new, tuple):
                    for r in runs:
                        if r is not keep:
                            p.remove(r)
                ts = keep.findall(qn("w:t"))
                for t in ts[1:]:
                    keep.remove(t)
                ts[0].text = new if isinstance(new, str) else new[0]
                ts[0].set(qn("xml:space"), "preserve")

    def save(self, path: str):
        self.doc.save(path)


def visible_text(docx_path: str) -> str:
    """All text a parser/ATS would read, incl. text boxes, in reading order."""
    d = Document(docx_path)
    chunks: list[str] = []
    for p in d.element.body.iter(qn("w:p")):
        s = "".join((t.text or "") if t.tag == qn("w:t") else ("\t" if t.tag == qn("w:tab") else "\n")
                    for t in p.iter() if t.tag in (qn("w:t"), qn("w:tab"), qn("w:br")))
        if s.strip():
            chunks.append(s)
    # de-duplicate the VML fallback copy of text boxes
    seen: set[str] = set()
    out = []
    for c in chunks:
        if c in seen and len(c) > 3:
            continue
        seen.add(c)
        out.append(c)
    return "\n".join(out)

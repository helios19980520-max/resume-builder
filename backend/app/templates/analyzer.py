"""
Generic template analysis: any resume .docx -> TemplateMap.

1. inventory():  every body paragraph (and text-box paragraph) with its text and formatting facts
                 (style, sizes, bold/italic/caps, numbering, tab runs, alignment, spacing).
2. classify():   the model assigns each paragraph a ROLE (see ROLES) and, for header-like lines,
                 a PATTERN with placeholders + the original values, so the engine can rebuild the
                 line with the right run formatting.
3. build_map():  validates the classification, derives the experience-block structure and the
                 length budgets, and packs everything into a TemplateMap dict that generic.py renders.
"""
from __future__ import annotations

import json
import logging
import re
import statistics
from typing import Any

from docx import Document
from docx.oxml.ns import qn

from .. import config, llm

log = logging.getLogger("analyzer")

ROLES = [
    "name_line", "contact_line",
    "heading_summary", "heading_skills", "heading_experience", "heading_education", "heading_other",
    "summary", "skill_line",
    "exp_header_1", "exp_header_2", "exp_header_3", "exp_scope", "exp_blurb", "exp_subheading",
    "exp_bullet", "exp_url",
    "edu_line",
    "blank", "static", "drawing",
]
PLACEHOLDERS = {
    "name_line": ["name", "headline"],
    "contact_line": ["location", "email", "phone", "linkedin", "github", "website"],
    "exp_header_1": ["company", "location", "remote", "role", "start", "end", "dates"],
    "exp_header_2": ["company", "location", "remote", "role", "start", "end", "dates"],
    "exp_header_3": ["company", "location", "remote", "role", "start", "end", "dates"],
    "exp_scope": ["tech_scope"],
    "exp_url": ["website"],
    "edu_line": ["degree", "field", "university", "start_year", "end_year", "years"],
}


# --------------------------------------------------------------------------- inventory
def _run_facts(r) -> dict:
    rpr = r.find(qn("w:rPr"))
    f = {"b": False, "i": False, "u": False, "caps": False, "sz": None, "tab": False, "br": False, "text": ""}
    f["text"] = "".join(t.text or "" for t in r.findall(qn("w:t")))
    f["tab"] = r.find(qn("w:tab")) is not None
    f["br"] = r.find(qn("w:br")) is not None
    if rpr is not None:
        def on(tag):
            el = rpr.find(qn(tag))
            return el is not None and el.get(qn("w:val")) not in ("0", "false")
        f["b"] = on("w:b") or (rpr.find(qn("w:rStyle")) is not None and rpr.find(qn("w:rStyle")).get(qn("w:val")) == "Strong")
        f["i"] = on("w:i")
        f["u"] = rpr.find(qn("w:u")) is not None
        f["caps"] = on("w:caps")
        sz = rpr.find(qn("w:sz"))
        if sz is not None:
            try:
                f["sz"] = int(sz.get(qn("w:val"))) / 2
            except Exception:
                pass
    return f


def _para_facts(p, idx: int, where: str = "body") -> dict:
    runs = [_run_facts(r) for r in p.iter(qn("w:r"))]
    text = "".join(("\t" if r["tab"] else "") + ("\n" if r["br"] else "") + r["text"] for r in runs)
    ppr = p.find(qn("w:pPr"))
    style = ""
    numbered = False
    align = ""
    ind = ""
    if ppr is not None:
        st = ppr.find(qn("w:pStyle"))
        style = st.get(qn("w:val")) if st is not None else ""
        num = ppr.find(qn("w:numPr"))
        if num is not None:
            nid = num.find(qn("w:numId"))
            numbered = nid is not None and nid.get(qn("w:val")) not in (None, "0")
        jc = ppr.find(qn("w:jc"))
        align = jc.get(qn("w:val")) if jc is not None else ""
        i = ppr.find(qn("w:ind"))
        if i is not None:
            ind = " ".join(f"{k.split('}')[1]}={v}" for k, v in i.attrib.items())
    text_runs = [r for r in runs if r["text"].strip()]
    sizes = [r["sz"] for r in text_runs if r["sz"]]
    return {
        "idx": idx, "where": where, "style": style, "text": text, "len": len(text.strip()),
        "empty": not text.strip(), "numbered": numbered, "align": align, "ind": ind,
        "tabs": sum(1 for r in runs if r["tab"]), "breaks": sum(1 for r in runs if r["br"]),
        "all_bold": bool(text_runs) and all(r["b"] for r in text_runs),
        "some_bold": any(r["b"] for r in text_runs) and not all(r["b"] for r in text_runs),
        "all_italic": bool(text_runs) and all(r["i"] for r in text_runs),
        "some_italic": any(r["i"] for r in text_runs),
        "caps": any(r["caps"] for r in text_runs),
        "size": statistics.median(sizes) if sizes else None,
        "has_drawing": p.find(".//" + qn("w:drawing")) is not None or p.find(".//" + qn("w:pict")) is not None,
    }


def inventory(docx_path: str) -> dict:
    d = Document(docx_path)
    body = [p._p for p in d.paragraphs]
    paras = [_para_facts(p, i) for i, p in enumerate(body)]
    # text boxes (e.g. a header band with the name) - only the first (DrawingML) copy
    tb: list[dict] = []
    seen_txbx = set()
    for i, p in enumerate(body):
        for txbx in p.iter(qn("w:txbxContent")):
            key = "".join(t.text or "" for t in txbx.iter(qn("w:t")))
            if key in seen_txbx:
                continue
            seen_txbx.add(key)
            for j, tp in enumerate(txbx.findall(qn("w:p"))):
                f = _para_facts(tp, len(tb), where=f"textbox(p{i})")
                f["tb_para"] = j
                tb.append(f)
    sec = d.sections[0]
    page = {
        "width_in": round(sec.page_width.inches, 2) if sec.page_width else None,
        "height_in": round(sec.page_height.inches, 2) if sec.page_height else None,
        "margins_in": [round(x.inches, 2) if x else None for x in (sec.top_margin, sec.bottom_margin, sec.left_margin, sec.right_margin)],
    }
    fonts = _fonts(d)
    return {"paragraphs": paras, "textbox_paragraphs": tb, "page": page, "fonts": fonts,
            "tables": len(d.tables)}


def _fonts(d) -> dict:
    out = {"theme_major": "", "theme_minor": "", "explicit": {}}
    try:
        theme = [p for p in d.part.package.parts if "theme" in str(p.partname)]
        if theme:
            xml = theme[0].blob.decode("utf-8", "ignore")
            m = re.findall(r'<a:latin typeface="([^"]*)"', xml)
            if m:
                out["theme_major"], out["theme_minor"] = m[0], (m[1] if len(m) > 1 else m[0])
    except Exception:
        pass
    counts: dict[str, int] = {}
    for r in d.element.body.iter(qn("w:rFonts")):
        f = r.get(qn("w:ascii"))
        if f:
            counts[f] = counts.get(f, 0) + 1
    out["explicit"] = dict(sorted(counts.items(), key=lambda kv: -kv[1])[:6])
    return out


# --------------------------------------------------------------------------- classification
CLASSIFY_SYSTEM = """You analyse the structure of resume templates stored as Word documents. You receive every
paragraph of a resume (in order) with formatting facts, and you label each one with a ROLE so a program can
rebuild the document with new content while keeping the exact formatting.

ROLES:
- name_line        the candidate's name (may include a headline in the same paragraph)
- contact_line     location / email / phone / links line
- heading_summary, heading_skills, heading_experience, heading_education   section headings.
                   An EMPTY paragraph that uses a heading style and sits where a heading belongs
                   (e.g. before the skills list or before the first job) is also a heading: label it and
                   provide heading_text (the natural title, e.g. "Skills & Abilities", "Experience").
- heading_other    any other section heading (Projects, Certifications ...) - keep its text
- summary          the professional summary paragraph(s)
- skill_line       one line/paragraph of the skills list
- exp_header_1     the FIRST paragraph of a job entry (e.g. company + dates, or role | company)
- exp_header_2     the second header line of a job entry (e.g. role title, or company + location)
- exp_header_3     a third header line if present
- exp_scope        a "Technical Scope:" / "Stack:" line listing technologies
- exp_blurb        an italic/one-paragraph description of the employer
- exp_subheading   a fixed label inside a job such as "Key Achievements:"
- exp_bullet       one achievement bullet / paragraph inside a job
- exp_url          a line holding the employer's website
- edu_line         education lines (degree, university, years)
- blank            empty spacer paragraph that is NOT a heading
- static           anything else to keep verbatim (footers, notes)
- drawing          paragraph holding an image/drawing (kept as-is)

For roles name_line, contact_line, exp_header_1/2/3, exp_scope, exp_url, edu_line also return:
  pattern: the paragraph text with the variable parts replaced by placeholders, keeping literal separators,
           brackets, labels and tabs exactly. Use "\\t" where the original used tabs for alignment and "\\n"
           for line breaks. Placeholders allowed:
           name_line: {name} {headline}
           contact_line: {location} {email} {phone} {linkedin} {github} {website}
           exp_header_*: {company} {location} {remote} {role} {start} {end} {dates}
           exp_scope: {tech_scope}  (keep the literal label, e.g. "Technical Scope: {tech_scope}")
           exp_url: {website}
           edu_line: {degree} {field} {university} {start_year} {end_year} {years}
  values: object mapping each placeholder used to the ORIGINAL text it replaced (exact substring).
Text-box paragraphs (where starts with "textbox") get the same roles (typically name_line / contact_line);
a contact line split over several text-box paragraphs is fine: label each one contact_line with its own pattern
(e.g. "{location}" and "{email}").

Also return template-level metadata. Describe the LAYOUT and STYLE, never the sample person's profession or
employers (the same template will be reused for other people):
  name (short style name, 2-4 words, e.g. "Classic Teal Serif", "Compact Two-Tone"), description (one sentence on the look),
  style_summary (3-4 sentences a recruiter would use: density, tone, colours, fonts, bullets vs prose,
  suited to which kinds of roles/industries/seniority), tone (one of: classic, modern, executive, compact,
  creative), best_for (list of 3-6 short phrases: role types / industries / seniority this layout suits).

Return ONLY JSON:
{"name":..., "description":..., "style_summary":..., "tone":..., "best_for":[...],
 "paragraphs":[{"where":"body"|"textbox","idx":int,"role":str,"pattern":str?,"values":{}?,"heading_text":str?}, ...]}
Every paragraph in the input must appear exactly once."""


def _fmt_inventory(inv: dict) -> str:
    lines = []
    for p in inv["paragraphs"] + inv["textbox_paragraphs"]:
        facts = []
        if p["style"]:
            facts.append(f"style={p['style']}")
        if p["size"]:
            facts.append(f"{p['size']:g}pt")
        if p["all_bold"]:
            facts.append("bold")
        elif p["some_bold"]:
            facts.append("partly-bold")
        if p["all_italic"]:
            facts.append("italic")
        elif p["some_italic"]:
            facts.append("partly-italic")
        if p["caps"]:
            facts.append("caps")
        if p["numbered"]:
            facts.append("bulleted")
        if p["tabs"]:
            facts.append(f"tabs={p['tabs']}")
        if p["breaks"]:
            facts.append(f"linebreaks={p['breaks']}")
        if p["has_drawing"]:
            facts.append("DRAWING")
        if p["ind"]:
            facts.append(f"ind({p['ind']})")
        txt = p["text"].replace("\t", "\\t").replace("\n", "\\n").strip()
        txt = txt if len(txt) <= 170 else txt[:167] + "..."
        where = "body" if p["where"] == "body" else "textbox"
        lines.append(f"[{where} {p['idx']}] ({', '.join(facts)}) {'<EMPTY>' if p['empty'] else txt}")
    return "\n".join(lines)


def classify(inv: dict) -> dict:
    user = ("Document facts: page " + json.dumps(inv["page"]) + ", fonts " + json.dumps(inv["fonts"]) +
            f", tables={inv['tables']}\n\nParagraphs:\n" + _fmt_inventory(inv))
    data = llm.complete_json(CLASSIFY_SYSTEM, user, model=config.CLAUDE_MODEL, max_tokens=16000)
    if not isinstance(data, dict) or "paragraphs" not in data:
        raise RuntimeError("template classification returned an unexpected shape")
    return data


# --------------------------------------------------------------------------- map building
class TemplateError(Exception):
    pass


def _norm_role(r: str) -> str:
    r = (r or "").strip().lower()
    aliases = {"heading": "heading_other", "bullet": "exp_bullet", "skill": "skill_line", "education": "edu_line",
               "name": "name_line", "contact": "contact_line", "spacer": "blank", "empty": "blank"}
    r = aliases.get(r, r)
    return r if r in ROLES else "static"


def build_map(docx_path: str, inv: dict, cls: dict, template_id: str, source_name: str) -> dict:
    body_n = len(inv["paragraphs"])
    tb_n = len(inv["textbox_paragraphs"])
    body: dict[int, dict] = {}
    tbox: dict[int, dict] = {}
    for item in cls.get("paragraphs", []):
        try:
            idx = int(item.get("idx"))
        except Exception:
            continue
        where = "textbox" if str(item.get("where", "body")).startswith("text") else "body"
        raw_values = item.get("values") or {}
        values = {str(k).strip("{} "): ("" if v is None else str(v)) for k, v in raw_values.items()} if isinstance(raw_values, dict) else {}
        entry = {"idx": idx, "role": _norm_role(item.get("role")),
                 "pattern": item.get("pattern") or "", "values": values,
                 "heading_text": item.get("heading_text") or ""}
        if where == "body" and 0 <= idx < body_n:
            body[idx] = entry
        elif where == "textbox" and 0 <= idx < tb_n:
            tbox[idx] = entry
    # fill gaps with heuristics
    for i, p in enumerate(inv["paragraphs"]):
        if i not in body:
            body[i] = {"idx": i, "role": "drawing" if p["has_drawing"] else ("blank" if p["empty"] else "static"),
                       "pattern": "", "values": {}, "heading_text": ""}
        # a paragraph that is ONLY a drawing (no text) is kept verbatim; text + decoration keeps its text role
        if inv["paragraphs"][i]["has_drawing"] and inv["paragraphs"][i]["empty"]:
            body[i]["role"] = "drawing"
    paras = [body[i] for i in range(body_n)]
    tb = [tbox.get(i, {"idx": i, "role": "static", "pattern": "", "values": {}, "heading_text": ""}) for i in range(tb_n)]

    roles = [p["role"] for p in paras] + [p["role"] for p in tb]
    missing = [r for r in ("summary", "skill_line", "exp_header_1", "exp_bullet") if r not in roles]
    if "name_line" not in roles:
        missing.append("name_line")
    if missing:
        raise TemplateError("Could not recognise these parts of the template: " + ", ".join(missing) +
                            ". Make sure the document has a name, a summary, a skills list and at least one job with bullets.")

    # --- experience block structure: from first exp_header_1 to the paragraph before the second exp_header_1
    exp_idx = [p["idx"] for p in paras if p["role"] == "exp_header_1"]
    first = exp_idx[0]
    # end of the experience zone = first paragraph after `first` whose role is a non-exp heading / edu / static
    stop_roles = {"heading_education", "heading_other", "edu_line", "static", "heading_skills", "heading_summary"}
    end = body_n
    for p in paras[first + 1:]:
        if p["role"] in stop_roles:
            end = p["idx"]
            break
    second = exp_idx[1] if len(exp_idx) > 1 else end
    block_roles = [paras[i]["role"] for i in range(first, second)]
    # strip trailing blanks that belong "between jobs" but keep one copy
    block = [{"idx": i, "role": paras[i]["role"]} for i in range(first, second)]
    if "exp_bullet" not in [b["role"] for b in block]:
        raise TemplateError("The first job entry has no bullet paragraphs; cannot learn the job layout.")

    # bullets per job across the whole zone
    bullets_per_job: list[int] = []
    cur = None
    for p in paras[first:end]:
        if p["role"] == "exp_header_1":
            if cur is not None:
                bullets_per_job.append(cur)
            cur = 0
        elif p["role"] == "exp_bullet" and cur is not None:
            cur += 1
    if cur is not None:
        bullets_per_job.append(cur)
    bullets_per_job = [b for b in bullets_per_job if b > 0] or [len([b for b in block if b["role"] == "exp_bullet"])]

    texts = {p["idx"]: inv["paragraphs"][p["idx"]]["text"] for p in paras}
    tb_texts = {p["idx"]: inv["textbox_paragraphs"][p["idx"]]["text"] for p in tb}

    def lens(role):
        return [len(texts[p["idx"]].strip()) for p in paras if p["role"] == role and texts[p["idx"]].strip()]

    summary_len = sum(lens("summary")) or 500
    skill_lens = lens("skill_line")
    bullet_lens = lens("exp_bullet")
    scope_lens = lens("exp_scope")
    blurb_lens = lens("exp_blurb")
    skill_paras = [inv["paragraphs"][p["idx"]] for p in paras if p["role"] == "skill_line"]
    labelled = bool(skill_paras) and sum(1 for s in skill_paras if s["some_bold"] and ":" in s["text"]) >= len(skill_paras) / 2
    bullet_paras = [inv["paragraphs"][p["idx"]] for p in paras if p["role"] == "exp_bullet"]
    bold_kw = bool(bullet_paras) and sum(1 for b in bullet_paras if b["some_bold"]) >= len(bullet_paras) / 2
    prose = bool(bullet_paras) and statistics.median([b["len"] for b in bullet_paras]) > 240 and not any(b["numbered"] for b in bullet_paras)

    def rng(v, lo_d, hi_d):
        if not v:
            return [lo_d, hi_d]
        lo, hi = min(v), max(v)
        return [max(20, lo - 5), hi + 5]

    budget = {
        "summary_chars": summary_len, "summary_tolerance": 0.08,
        "skill_lines": len(skill_lens) or 6, "skill_line_chars": rng(skill_lens, 30, 120), "skill_labelled": labelled,
        "total_bullets": sum(bullets_per_job), "bullets_per_job_original": bullets_per_job,
        "bullet_chars": rng(bullet_lens, 120, 260), "bullet_avg": int(statistics.mean(bullet_lens)) if bullet_lens else 190,
        "tech_scope_chars": rng(scope_lens, 150, 300) if scope_lens else None,
        "blurb_chars": rng(blurb_lens, 200, 380) if blurb_lens else None,
        "bold_keywords": bold_kw,
        "voice": ("First-person prose paragraphs (2-3 sentences) that read like an engineer talking about the work; "
                  "'I' allowed but sparse." if prose else
                  "Achievement bullets starting with a past-tense verb; one sentence, sometimes two; concrete component "
                  "names and numbers." + (" Wrap 2-4 key technologies/outcomes per bullet in **double asterisks**." if bold_kw else "")),
    }

    return {
        "id": template_id, "source_name": source_name,
        "name": cls.get("name") or source_name, "description": cls.get("description") or "",
        "style_summary": cls.get("style_summary") or "", "tone": cls.get("tone") or "",
        "best_for": cls.get("best_for") or [],
        "page": inv["page"], "fonts": inv["fonts"],
        "paragraphs": paras, "textbox_paragraphs": tb,
        "texts": {str(k): v for k, v in texts.items()}, "textbox_texts": {str(k): v for k, v in tb_texts.items()},
        "experience": {"first": first, "end": end, "block": block, "block_roles": block_roles},
        "budget": budget,
        "features": {"prose": prose, "bold_keywords": bold_kw, "labelled_skills": labelled,
                     "has_textbox_header": any(p["role"] in ("name_line", "contact_line") for p in tb),
                     "has_scope": bool(scope_lens), "has_blurb": bool(blurb_lens),
                     "jobs_in_original": len(bullets_per_job), "summary_chars": summary_len,
                     "skill_lines": len(skill_lens), "avg_bullet_chars": budget["bullet_avg"]},
    }


def analyze_docx(docx_path: str, template_id: str, source_name: str) -> dict:
    inv = inventory(docx_path)
    if len(inv["paragraphs"]) < 8:
        raise TemplateError("This document has too few paragraphs to be a resume template.")
    if inv["tables"]:
        log.warning("template %s contains %d table(s); table content is kept verbatim", template_id, inv["tables"])
    cls = classify(inv)
    return build_map(docx_path, inv, cls, template_id, source_name)

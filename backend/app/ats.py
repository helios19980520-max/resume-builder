"""
Self ATS scoring. Deterministic and explainable - every point is traceable to a check,
so the user can see WHY the score is what it is, and what to change.

Weights (100):
  40  keyword coverage   - JD/company ATS keywords found in the resume (top-weighted list)
  10  title alignment    - JD role title words appear in headline/summary
  10  section integrity  - contact, summary, skills, experience with dates, education
  10  parse friendliness - no tables/images/text boxes that break parsers, standard fonts, dates parse
  10  measurable results - share of bullets that carry a number
  10  human writing      - banned words / pronouns / patterns (from humanize.py) + readability
  10  template fit       - lengths within the template budgets (layout will not break)
"""
from __future__ import annotations

import re
from typing import Iterable

from .humanize import find_flags, readability
from .models import ATSCheck, ATSReport, JDIntel, ResumeContent
from .templates.engine import strip_md
from .templates.registry import TemplateSpec

ALIASES = {
    "javascript": ["js", "es6", "es6+", "ecmascript"],
    "typescript": ["ts"],
    "react": ["react.js", "reactjs"],
    "node.js": ["node", "nodejs"],
    "postgresql": ["postgres", "psql"],
    "kubernetes": ["k8s"],
    "amazon web services": ["aws"],
    "aws": ["amazon web services"],
    "google cloud": ["gcp", "google cloud platform"],
    "ci/cd": ["ci cd", "continuous integration", "continuous delivery", "continuous deployment"],
    "rest": ["restful", "rest api", "rest apis"],
    "microservices": ["micro-services", "microservice"],
    "machine learning": ["ml"],
    "artificial intelligence": ["ai"],
    "large language model": ["llm", "llms"],
    "next.js": ["nextjs", "next"],
    "vue": ["vue.js", "vuejs"],
    "golang": ["go"],
    "c#": ["csharp", ".net"],
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


_STOP = {"and", "or", "with", "the", "a", "an", "of", "in", "on", "for", "to", "such", "as", "similar", "experience",
         "strong", "knowledge", "skills", "using", "ability", "years", "building", "design", "systems", "system"}


def _present(kw: str, text: str) -> bool:
    k = _norm(kw)
    cands = {k} | set(ALIASES.get(k, []))
    for a, al in ALIASES.items():
        if k in al:
            cands.add(a)
    for c in cands:
        pat = r"(?<![\w])" + re.escape(c) + r"(?![\w])"
        if re.search(pat, text):
            return True
    # descriptive phrases ("PostgreSQL (schema design and query tuning)", "6+ years building web applications"):
    # count as present when the head term and most significant tokens appear
    head = re.split(r"[(\-–:,]", k)[0].strip()
    if head and head != k and _present(head, text):
        return True
    toks = [t for t in re.findall(r"[a-z0-9+#.]+", k) if t not in _STOP and len(t) > 2]
    if len(toks) >= 2:
        hit = sum(1 for t in toks if re.search(r"(?<![\w])" + re.escape(t) + r"(?![\w])", text))
        return hit / len(toks) >= 0.6
    return False


def _resume_text(c: ResumeContent) -> str:
    parts = [c.full_name, c.headline, c.location, c.summary]
    parts += [f"{s.label} {s.items}" for s in c.skills]
    for e in c.experiences:
        parts += [e.company, e.role, e.tech_scope, e.company_blurb] + e.bullets
    ed = c.education
    parts += [ed.university, ed.degree, ed.field]
    return _norm(strip_md(" \n ".join(p for p in parts if p)))


def _dates_ok(exps: Iterable) -> bool:
    rx = re.compile(r"(\d{1,2}/\d{4}|\d{4}|[A-Za-z]{3,9}\.? \d{4}|present|current|now)", re.I)
    return all(rx.search(e.start or "") and rx.search(e.end or "") for e in exps)


def _grade(t: float) -> str:
    return "A" if t >= 88 else "B" if t >= 76 else "C" if t >= 64 else "D" if t >= 50 else "E"


def score(spec: TemplateSpec, intel: JDIntel, c: ResumeContent, docx_visible_text: str | None = None) -> ATSReport:
    text = _resume_text(c)
    if docx_visible_text:
        text = _norm(text + " " + docx_visible_text)
    checks: list[ATSCheck] = []

    # 1. keyword coverage (weighted by rank)
    kws = [k for k in intel.ats_keywords if k.strip()]
    must = [k for k in intel.must_have_skills if k.strip()]
    ordered = list(dict.fromkeys(must + kws))[:45]
    matched, missing = [], []
    wsum = wgot = 0.0
    for i, k in enumerate(ordered):
        w = 1.5 if k in must else (1.2 if i < 10 else 1.0)
        wsum += w
        if _present(k, text):
            matched.append(k)
            wgot += w
        else:
            missing.append(k)
    cov = (wgot / wsum) if wsum else 1.0
    checks.append(ATSCheck(name="Keyword coverage", score=round(40 * cov, 1), max_score=40,
                           detail=f"{len(matched)}/{len(ordered)} JD + industry keywords found "
                                  f"(must-have skills weighted 1.5x).",
                           items=missing[:15]))

    # 2. title alignment
    title_words = [w for w in re.findall(r"[a-z][a-z.+#]+", _norm(intel.role_title)) if w not in
                   {"and", "or", "the", "of", "a", "an", "to", "for", "with", "in"}]
    head = _norm(c.headline + " " + c.summary[:300])
    hit = sum(1 for w in title_words if w in head)
    t_score = 10 * (hit / len(title_words)) if title_words else 10
    checks.append(ATSCheck(name="Title alignment", score=round(t_score, 1), max_score=10,
                           detail=f"Headline '{c.headline}' vs JD title '{intel.role_title}': {hit}/{len(title_words)} title words present."))

    # 3. section integrity
    s = 0.0
    notes = []
    if c.contact.email or c.contact.phone or c.contact.linkedin:
        s += 2
    else:
        notes.append("no contact method")
    if len(c.summary) > 200:
        s += 2
    else:
        notes.append("summary short/missing")
    if len(c.skills) >= 4:
        s += 2
    else:
        notes.append("skills section thin")
    if c.experiences and all(e.bullets for e in c.experiences) and _dates_ok(c.experiences):
        s += 3
    else:
        notes.append("experience entries missing bullets or parseable dates")
    if c.education.university and c.education.degree:
        s += 1
    else:
        notes.append("education incomplete")
    checks.append(ATSCheck(name="Section integrity", score=s, max_score=10,
                           detail="Contact, summary, skills, dated experience, education." + (" Issues: " + "; ".join(notes) if notes else ""),
                           items=notes))

    # 4. parse friendliness (template-level facts)
    pf = 10.0
    pf_notes = []
    if spec.features.get("has_textbox_header"):
        pf -= 2.5
        pf_notes.append("name/contact sit in a header text box - most modern parsers read it, older ones may not")
    common = {"calibri", "cambria", "arial", "times new roman", "georgia", "helvetica", "garamond", "verdana", "tahoma", "segoe ui"}
    odd = [f for f in (spec.map.get("fonts") or {}).get("explicit", {}) if f.lower() not in common]
    if odd:
        pf -= 0.5
        pf_notes.append(f"non-standard font(s) {', '.join(odd[:3])}: fine in PDF (embedded), may substitute in .docx on other machines")
    if spec.features.get("prose"):
        pf -= 0.5
        pf_notes.append("prose paragraphs instead of bullets: some parsers split achievements less cleanly")
    if not _dates_ok(c.experiences):
        pf -= 3
        pf_notes.append("dates not in a standard format")
    checks.append(ATSCheck(name="Parse friendliness", score=round(pf, 1), max_score=10,
                           detail="No tables, single column, standard headings, real text (no images of text)."
                                  + (" " + "; ".join(pf_notes) if pf_notes else ""), items=pf_notes))

    # 5. measurable results
    bullets = [strip_md(b) for e in c.experiences for b in e.bullets]
    with_num = [b for b in bullets if re.search(r"\d", b)]
    ratio = len(with_num) / max(1, len(bullets))
    # sweet spot 40-70%
    m_score = 10 * min(1.0, ratio / 0.45) if ratio <= 0.7 else 10 - (ratio - 0.7) * 15
    checks.append(ATSCheck(name="Measurable results", score=round(max(0, m_score), 1), max_score=10,
                           detail=f"{len(with_num)}/{len(bullets)} bullets carry a number ({ratio:.0%}); 40-70% reads natural."))

    # 6. human writing
    flags = []
    for e in c.experiences:
        for b in e.bullets:
            flags += [f for f in find_flags(b)]
    flags += find_flags(c.summary)
    whole_flags = [f for f in find_flags(" ".join([c.summary] + bullets)) if f.startswith("overused")]
    flags = list(dict.fromkeys(flags + whole_flags))
    rd = readability(" ".join([c.summary] + bullets))
    h = 10 - min(8, 0.8 * len(flags))
    if rd["avg_sentence_words"] > 34:
        h -= 1
    if rd["long_word_ratio"] > 0.12:
        h -= 1
    checks.append(ATSCheck(name="Human writing", score=round(max(0, h), 1), max_score=10,
                           detail=f"{len(flags)} flagged words/patterns; avg sentence {rd['avg_sentence_words']} words; "
                                  f"long-word ratio {rd['long_word_ratio']:.1%}.", items=flags[:20]))

    # 7. template fit
    from .writer import _count_lengths  # local import to avoid cycle
    probs = _count_lengths(spec, c)
    tf = 10 - min(10, 1.5 * len(probs))
    b = spec.budget
    length_report = {
        "summary_chars": len(strip_md(c.summary)), "summary_target": b.summary_chars,
        "skill_lines": len(c.skills), "skill_lines_target": b.skill_lines,
        "bullets_per_company": [len(e.bullets) for e in c.experiences],
        "bullets_target": spec.bullets_per_company(len(c.experiences)),
        "avg_bullet_chars": round(sum(len(x) for x in bullets) / max(1, len(bullets))),
        "bullet_avg_target": b.bullet_avg,
        "problems": probs,
    }
    checks.append(ATSCheck(name="Template fit", score=round(tf, 1), max_score=10,
                           detail=f"Summary {length_report['summary_chars']}/{b.summary_chars} chars, "
                                  f"{len(c.skills)}/{b.skill_lines} skill lines, avg bullet "
                                  f"{length_report['avg_bullet_chars']}/{b.bullet_avg} chars.", items=probs[:10]))

    total = round(sum(ch.score for ch in checks), 1)
    return ATSReport(total=total, grade=_grade(total), checks=checks, matched_keywords=matched,
                     missing_keywords=missing, flagged_phrases=flags, length_report=length_report)

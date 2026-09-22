"""
Step 3: write the resume content for the chosen template.

  draft (best model)  ->  mechanical checks (length budgets, banned words, pronouns, keyword coverage)
                      ->  targeted fix pass (fast model) x up to 2
  revise(feedback)    ->  same loop, seeded with the current content
"""
from __future__ import annotations

import json
import logging
import re
from typing import Callable

from . import config, llm
from .humanize import HUMAN_RULES, find_flags
from .models import Experience, JDIntel, ProfileInput, ResumeContent, SkillLine
from .templates.engine import strip_md
from .templates.registry import TemplateSpec

log = logging.getLogger("writer")
Progress = Callable[[str], None]

WRITER_SYSTEM = """You are a senior engineer who has hired for and written many resumes, ghost-writing for a
real candidate. The resume must (a) read as written by a person, (b) pass the company's ATS by carrying the
right vocabulary, and (c) fit an existing Word template whose layout breaks if text lengths drift.

""" + HUMAN_RULES + """

CONTENT RULES:
- Summary: rewrite it so the hiring team recognises their own problem in it. Weave in one of the company's
  own phrases/values naturally (not as a quote), the candidate's stance on the kind of engineering this role
  needs, and the strongest 3-4 matching skills. No list of years/companies. Personal but not fluffy.
- Skills: order and pick lines by what the JD wants first. Keep every line short enough for the budget.
  Only list skills that are plausible for someone with this history; reorder/add/remove to mirror the JD.
- Experience bullets: for EACH company, tell believable stories that someone at that company in that
  role would have lived, built from the company profile (its actual products/domain) AND shaped so that
  the JD's required experience shows up where it can honestly fit. Use the story hooks from the analysis
  when they fit the company's domain. Every bullet: what was built/changed, on which component, what
  went wrong or what constraint existed, what the result was. Vary structure. Include the JD's ATS keywords
  wherever they are true for the work.
- Tech scope lines: ONLY a comma-separated list of technology names used at that job (e.g. "TypeScript, Node.js,
  PostgreSQL, Redis, Kafka, AWS ECS, GitHub Actions") - no sentences, no verbs, matching the bullets.
- Dates/companies/roles/education: copy the candidate's facts exactly; never invent employers.
- Title/headline: match the JD's role title unless the candidate's headline is clearly closer.

TEMPLATE FIT (hard): respect the character budgets given below (±8%). Counts are characters INCLUDING spaces.
For skills, produce exactly the requested number of lines. For bullets, produce exactly the requested count
per company and keep each within the min/max. Where the template uses **bold**, wrap 2-4 key technologies or
outcomes per bullet in double asterisks; otherwise use no markdown at all."""

WRITER_USER = """<template>
id: {tid}
voice: {voice}
budgets:
  summary_chars: {summary_chars} (±8%)
  skill_lines: exactly {skill_lines}; each {skill_min}-{skill_max} chars{skill_label_note}
  bullets_per_company (in the order the companies are listed): {bullets_per_company}
  bullet_chars: {bullet_min}-{bullet_max}, aim around {bullet_avg}
  {tech_scope_note}
  {blurb_note}
  bold_keywords: {bold}
</template>

<job_analysis>
{intel}
</job_analysis>

<candidate>
{profile}
</candidate>

<candidate_company_profiles>
{company_profiles}
</candidate_company_profiles>

{feedback_block}

Return ONE JSON object:
{{
  "full_name": str, "headline": str, "location": str,
  "contact": {{"email": str, "phone": str, "linkedin": str, "github": str, "website": str}},
  "summary": str,
  "skills": [{{"label": str, "items": str}}, ...],          # label "" unless template wants labels
  "experiences": [
     {{"company": str, "location": str, "remote": bool, "role": str, "start": str, "end": str,
       "website": str, "company_blurb": str, "tech_scope": str, "bullets": [str, ...]}}, ...
  ],
  "education": {{"university": str, "degree": str, "field": str, "start_year": str, "end_year": str}}
}}"""

FIX_SYSTEM = """You edit resume JSON to fix specific mechanical problems without changing meaning or voice.
Change ONLY the fields named in the problem list; keep everything else byte-identical. Keep the writing plain
and human; do not introduce new problems from the banned list.

""" + HUMAN_RULES


def _count_lengths(spec: TemplateSpec, c: ResumeContent) -> list[str]:
    """Return list of budget problems, phrased for the fix pass."""
    b = spec.budget
    problems: list[str] = []
    tol = b.summary_tolerance
    s_len = len(strip_md(c.summary))
    lo, hi = int(b.summary_chars * (1 - tol)), int(b.summary_chars * (1 + tol))
    if not lo <= s_len <= hi:
        problems.append(f"summary is {s_len} chars; must be between {lo} and {hi}")
    if len(c.skills) != b.skill_lines:
        problems.append(f"skills has {len(c.skills)} lines; must have exactly {b.skill_lines}")
    for i, s in enumerate(c.skills):
        n = len(s.items) + (len(s.label) + 2 if b.skill_labelled else 0)
        if not b.skill_line_chars[0] <= n <= b.skill_line_chars[1] + 6:
            problems.append(f"skills[{i}] is {n} chars; must be {b.skill_line_chars[0]}-{b.skill_line_chars[1]}")
    want = spec.bullets_per_company(len(c.experiences))
    for i, e in enumerate(c.experiences):
        if len(e.bullets) != want[i]:
            problems.append(f"experiences[{i}].bullets has {len(e.bullets)} items; must have exactly {want[i]}")
        for j, bl in enumerate(e.bullets):
            n = len(strip_md(bl))
            if not b.bullet_chars[0] - 10 <= n <= b.bullet_chars[1] + 15:
                problems.append(f"experiences[{i}].bullets[{j}] is {n} chars; must be {b.bullet_chars[0]}-{b.bullet_chars[1]}")
        if b.tech_scope_chars:
            n = len(e.tech_scope)
            if not b.tech_scope_chars[0] - 30 <= n <= b.tech_scope_chars[1] + 20:
                problems.append(f"experiences[{i}].tech_scope is {n} chars; must be {b.tech_scope_chars[0]}-{b.tech_scope_chars[1]}")
        if b.blurb_chars:
            n = len(e.company_blurb)
            if not b.blurb_chars[0] - 30 <= n <= b.blurb_chars[1] + 30:
                problems.append(f"experiences[{i}].company_blurb is {n} chars; must be {b.blurb_chars[0]}-{b.blurb_chars[1]}")
        if b.bold_keywords:
            for j, bl in enumerate(e.bullets):
                if bl.count("**") < 2:
                    problems.append(f"experiences[{i}].bullets[{j}] needs 1-4 **bold** spans (wrap key technologies/outcomes)")
        elif any("**" in bl for bl in e.bullets):
            problems.append(f"experiences[{i}].bullets must not contain ** markdown for this template")
        if b.tech_scope_chars and e.tech_scope and re.search(r"\b(and|with|for|behind|runs|using)\b", e.tech_scope) \
                and e.tech_scope.count(",") < 5:
            problems.append(f"experiences[{i}].tech_scope must be a plain comma-separated list of technology names (no sentences)")
    return problems


def _style_problems(c: ResumeContent) -> list[str]:
    problems: list[str] = []
    fl = find_flags(c.summary)
    if fl:
        problems.append("summary: " + "; ".join(fl))
    for i, e in enumerate(c.experiences):
        for j, bl in enumerate(e.bullets):
            fl = find_flags(bl)
            if fl:
                problems.append(f"experiences[{i}].bullets[{j}]: " + "; ".join(fl))
        if e.company_blurb:
            fl = find_flags(e.company_blurb)
            if fl:
                problems.append(f"experiences[{i}].company_blurb: " + "; ".join(fl))
    # whole-document overuse
    whole = " ".join([c.summary] + [b for e in c.experiences for b in e.bullets])
    for f in find_flags(whole):
        if f.startswith("overused"):
            problems.append("whole resume: " + f)
    # repeated openers
    for i, e in enumerate(c.experiences):
        openers = [(re.findall(r"\w+", strip_md(b)) or [""])[0].lower() for b in e.bullets if b.strip()]
        openers = [o for o in openers if o]
        for k in range(len(openers) - 2):
            if openers[k] == openers[k + 1] == openers[k + 2]:
                problems.append(f"experiences[{i}].bullets[{k}-{k+2}] start with the same verb '{openers[k]}'")
                break
    return problems


def _profile_for_llm(p: ProfileInput) -> str:
    return json.dumps(p.model_dump(), ensure_ascii=False, indent=1)


def _intel_for_llm(intel: JDIntel) -> str:
    d = intel.model_dump()
    d.pop("plain_summary", None)
    d.pop("sources", None)
    return json.dumps(d, ensure_ascii=False, indent=1)


def _parse_content(data: dict, profile: ProfileInput) -> ResumeContent:
    # coerce + protect the facts the candidate typed
    exps = []
    llm_exps = [e for e in (data.get("experiences") or []) if isinstance(e, dict)]
    # one entry per company the candidate typed, in the candidate's order; match by name, else by position
    for i, src in enumerate(profile.companies):
        e = next((x for x in llm_exps if str(x.get("company", "")).strip().lower() == src.name.strip().lower()), None)
        if e is None:
            e = llm_exps[i] if i < len(llm_exps) else {}
        exps.append(Experience(
            company=src.name,
            location=src.location,
            remote=src.remote,
            role=src.role_title or str(e.get("role") or "Software Engineer"),
            start=src.start,
            end=src.end or "Present",
            website=src.website or str(e.get("website") or ""),
            company_blurb=str(e.get("company_blurb") or ""),
            tech_scope=str(e.get("tech_scope") or ""),
            bullets=[str(b).strip() for b in (e.get("bullets") or []) if str(b).strip()],
        ))
    skills = [SkillLine(label=str(s.get("label", "") or ""), items=str(s.get("items", "")))
              if isinstance(s, dict) else SkillLine(items=str(s)) for s in data.get("skills", [])]
    edu = profile.education
    return ResumeContent(
        full_name=profile.full_name,
        headline=data.get("headline") or profile.headline,
        location=profile.location,
        contact=profile.contact,
        summary=str(data.get("summary", "")).strip(),
        skills=skills,
        experiences=exps,
        education={"university": edu.university, "degree": edu.degree, "field": edu.field,
                   "start_year": edu.start_year, "end_year": edu.end_year},
    )


def _template_block(spec: TemplateSpec, n_companies: int) -> dict:
    b = spec.budget
    return dict(
        tid=spec.id, voice=b.voice, summary_chars=b.summary_chars, skill_lines=b.skill_lines,
        skill_min=b.skill_line_chars[0], skill_max=b.skill_line_chars[1],
        skill_label_note=(" ; each line has a short label (e.g. Languages, Frameworks, Databases, Cloud / Infrastructure, "
                          "Testing / Observability, Tools / Practices) - label counts toward the budget"
                          if b.skill_labelled else " ; no labels, items separated by ' / '"),
        bullets_per_company=spec.bullets_per_company(n_companies),
        bullet_min=b.bullet_chars[0], bullet_max=b.bullet_chars[1], bullet_avg=b.bullet_avg,
        tech_scope_note=(f"tech_scope_chars: {b.tech_scope_chars[0]}-{b.tech_scope_chars[1]} (comma-separated technologies)"
                         if b.tech_scope_chars else "tech_scope: leave empty string"),
        blurb_note=(f"company_blurb_chars: {b.blurb_chars[0]}-{b.blurb_chars[1]} (italic one-paragraph description of the "
                    "company and the candidate's place in it, first person allowed)" if b.blurb_chars
                    else "company_blurb: leave empty string"),
        bold=str(b.bold_keywords).lower(),
    )


def _keyword_problems(intel: JDIntel | None, content: ResumeContent, limit: int = 8) -> list[str]:
    """Top-ranked JD keywords that never appear in the resume -> one fix instruction."""
    if intel is None:
        return []
    from .ats import _present, _resume_text  # local import to avoid a cycle
    text = _resume_text(content)
    ranked = list(dict.fromkeys([k for k in intel.must_have_skills if k.strip()] + intel.ats_keywords[:25]))
    missing = [k for k in ranked if not _present(k, text)][:limit]
    if not missing:
        return []
    return ["keywords missing from the whole resume: " + ", ".join(missing) +
            " - work each one into an existing bullet, the summary or a skills line where it is TRUE for the candidate "
            "(rewrite that bullet naturally, keep its length within budget); skip any that would be a lie"]


def _fix_loop(spec: TemplateSpec, content: ResumeContent, profile: ProfileInput, progress: Progress,
              rounds: int = 3, intel: JDIntel | None = None) -> ResumeContent:
    for r in range(rounds):
        problems = _count_lengths(spec, content) + _style_problems(content)
        if r == 0:
            problems += _keyword_problems(intel, content)
        if not problems:
            break
        progress(f"Tightening {len(problems)} spots (length / wording / keywords)…")
        log.info("fix round %d (%d problems): %s", r + 1, len(problems), problems[:40])
        data = llm.complete_json(
            FIX_SYSTEM,
            "Current resume JSON:\n" + json.dumps(content.model_dump(), ensure_ascii=False, indent=1)
            + "\n\nProblems to fix (and nothing else):\n- " + "\n- ".join(problems)
            + "\n\nReturn the complete corrected JSON object with the same schema.",
            model=config.CLAUDE_MODEL if r == 0 else config.CLAUDE_FAST_MODEL, max_tokens=12000)
        content = _parse_content(data, profile)
    return content


def write_resume(spec: TemplateSpec, intel: JDIntel, profile: ProfileInput, company_profiles: dict[str, str],
                 progress: Progress = lambda m: None) -> ResumeContent:
    progress("Drafting the resume for this role…")
    tb = _template_block(spec, len(profile.companies))
    user = WRITER_USER.format(**tb, intel=_intel_for_llm(intel), profile=_profile_for_llm(profile),
                              company_profiles=json.dumps(company_profiles, ensure_ascii=False, indent=1),
                              feedback_block="")
    data = llm.complete_json(WRITER_SYSTEM, user, model=config.CLAUDE_MODEL, max_tokens=16000)
    content = _parse_content(data, profile)
    return _fix_loop(spec, content, profile, progress, intel=intel)


def revise_resume(spec: TemplateSpec, intel: JDIntel, profile: ProfileInput, company_profiles: dict[str, str],
                  current: ResumeContent, feedback: str, progress: Progress = lambda m: None) -> ResumeContent:
    progress("Applying your feedback…")
    tb = _template_block(spec, len(profile.companies))
    fb = ("<current_resume_json>\n" + json.dumps(current.model_dump(), ensure_ascii=False, indent=1)
          + "\n</current_resume_json>\n\n<user_feedback>\n" + feedback + "\n</user_feedback>\n\n"
          "Apply the feedback. Keep everything the feedback does not touch as close to the current text as "
          "possible (same bullets, same order) so the user recognises the document.")
    user = WRITER_USER.format(**tb, intel=_intel_for_llm(intel), profile=_profile_for_llm(profile),
                              company_profiles=json.dumps(company_profiles, ensure_ascii=False, indent=1),
                              feedback_block=fb)
    data = llm.complete_json(WRITER_SYSTEM, user, model=config.CLAUDE_MODEL, max_tokens=16000)
    content = _parse_content(data, profile)
    return _fix_loop(spec, content, profile, progress, intel=intel)


def remaining_problems(spec: TemplateSpec, content: ResumeContent) -> dict:
    return {"length": _count_lengths(spec, content), "style": _style_problems(content)}

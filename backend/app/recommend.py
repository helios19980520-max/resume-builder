"""Rank the template library against a job analysis: which layout suits this role/company best."""
from __future__ import annotations

import json
import logging

from . import config, llm
from .models import JDIntel, TemplateScore
from .templates.registry import TemplateSpec

log = logging.getLogger("recommend")

SYSTEM = """You are a senior technical recruiter choosing which resume LAYOUT to send for a specific job.
You get a hiring brief (industry, seniority, culture, what they value) and a list of resume templates described
by their style, density, tone and structure. Judge fit on: seniority signal (executive vs compact), industry
culture (startup vs enterprise vs deep-tech), how much room the candidate needs for concrete achievements vs
narrative, whether bold keywords / labelled skills help this ATS-heavy or human-read process, region norms
(A4 vs Letter), and the number of positions the template was designed for.
Return ONLY JSON: {"ranking":[{"template_id":str,"score":int 0-100,"reason":"one plain sentence"} ...]}
including EVERY template exactly once, best first. Scores must differ; be decisive."""


def _brief(intel: JDIntel) -> dict:
    return {"company": intel.company_name, "role": intel.role_title, "seniority": intel.seniority,
            "industry": intel.industry, "sub_industry": intel.sub_industry, "location": intel.location,
            "culture": intel.culture_signals[:6], "achievements_wanted": intel.achievements_wanted[:6],
            "preferred_experience": intel.preferred_experience[:6], "tech_stack": intel.tech_stack[:10],
            "hiring_goal": intel.hiring_goal}


def _heuristic(intel: JDIntel, templates: list[TemplateSpec]) -> list[TemplateScore]:
    senior = any(w in (intel.seniority + " " + intel.role_title).lower() for w in ("senior", "staff", "lead", "principal", "head"))
    out = []
    for t in templates:
        s = 60
        if senior and t.tone in ("executive", "classic"):
            s += 12
        if not senior and t.tone in ("compact", "modern"):
            s += 12
        if t.budget.bold_keywords and len(intel.ats_keywords) > 30:
            s += 6
        if t.features.get("prose") and any(w in intel.industry.lower() for w in ("research", "hpc", "gpu", "systems", "deep")):
            s += 8
        out.append(TemplateScore(template_id=t.id, score=min(99, s), reason="Heuristic fit based on seniority and layout density."))
    out.sort(key=lambda x: -x.score)
    return out


def rank_templates(intel: JDIntel, templates: list[TemplateSpec]) -> list[TemplateScore]:
    if not templates:
        return []
    if len(templates) == 1:
        return [TemplateScore(template_id=templates[0].id, score=90, reason="Only template in the library.")]
    cards = [{"template_id": t.id, "name": t.name, "tone": t.tone, "style_summary": t.style_summary,
              "best_for": t.best_for, "page": t.page,
              "structure": {"prose_paragraphs": t.features.get("prose"), "bold_keywords": t.budget.bold_keywords,
                            "labelled_skills": t.budget.skill_labelled, "jobs_designed_for": t.features.get("jobs_in_original"),
                            "bullets_total": t.budget.total_bullets, "summary_chars": t.budget.summary_chars}}
             for t in templates]
    try:
        data = llm.complete_json(SYSTEM, "<hiring_brief>\n" + json.dumps(_brief(intel), ensure_ascii=False)
                                 + "\n</hiring_brief>\n\n<templates>\n" + json.dumps(cards, ensure_ascii=False) + "\n</templates>",
                                 model=config.fast_model(), max_tokens=3000)
        ranking = data.get("ranking") if isinstance(data, dict) else data
        ids = {t.id for t in templates}
        out = []
        seen = set()
        for r in ranking or []:
            tid = str(r.get("template_id", ""))
            if tid in ids and tid not in seen:
                seen.add(tid)
                out.append(TemplateScore(template_id=tid, score=int(max(0, min(100, int(r.get("score", 50))))),
                                         reason=str(r.get("reason", ""))[:300]))
        for t in templates:  # anything the model forgot
            if t.id not in seen:
                out.append(TemplateScore(template_id=t.id, score=40, reason="Not ranked by the model."))
        out.sort(key=lambda x: -x.score)
        return out
    except Exception as e:
        log.warning("template ranking failed, using heuristic: %s", e)
        return _heuristic(intel, templates)

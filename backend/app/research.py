"""
Step 1: analyse the job description and research the company.

  fetch JD -> extract facts (fast model)
           -> ~10 targeted web searches (company, products, focus, news, engineering blog,
              slogans, competitors, partners, hiring/culture, LinkedIn posts)
           -> synthesis pass (best model) -> JDIntel incl. a plain-language summary for the UI
"""
from __future__ import annotations

import json
import logging
from typing import Callable

from . import config, llm, search
from .models import JDIntel

log = logging.getLogger("research")

Progress = Callable[[str], None]

EXTRACT_SYSTEM = """You read job descriptions and pull out structured facts. Be literal: only report what the
text supports. Missing -> empty string / empty list."""

EXTRACT_USER = """Job description page text (may include page chrome; ignore navigation/boilerplate):

<jd>
{jd}
</jd>

Return JSON with keys:
company_name, company_website (if visible), role_title, location, employment_type, seniority,
industry_guess, product_hints (list: product names / systems mentioned),
key_responsibilities (list, verbatim-ish, 6-12 items),
must_have_skills (list of concrete technologies / skills marked required),
nice_to_have_skills (list),
years_experience (string),
preferred_experience (list: kinds of experience they say they prefer),
domain_knowledge (list: domain/industry knowledge they want),
soft_signals (list: phrases about culture, values, how the team works),
ats_keywords (list: 25-40 exact terms an ATS would match on for this role, most important first,
  as they appear in the JD e.g. "TypeScript", "event-driven", "PostgreSQL", "payment reconciliation"),
jd_clean (the job description text cleaned of navigation and boilerplate, max 6000 chars)."""

SYNTH_SYSTEM = """You are a senior technical recruiter and industry analyst preparing a hiring brief. You combine a
job description with web research about the company. Where research is thin, say so briefly rather than
inventing facts. Prefer concrete names (products, components, competitors, partners) over generalities.
Keep the plain-language summary in short everyday words: a candidate should understand it in 60 seconds."""

SYNTH_USER = """<jd_facts>
{facts}
</jd_facts>

<web_research>
{research}
</web_research>

Produce ONE JSON object with exactly these keys:

company_name, company_website, role_title, location, employment_type, seniority,
industry (one short label, e.g. "Online travel booking (OTA)", "Healthcare SaaS", "iGaming"),
sub_industry (one short phrase),
company_summary (2-3 sentences, what they do and for whom),
products (list of product / service names with a few words each),
current_projects (list: what they are visibly building or rolling out now),
projects_plain (list of 3-6 strings, each "Project or product name – one or two short sentences in everyday words a
  non-engineer would understand: what it is, who uses it, and what the team is doing with it right now"),
current_focus (list: strategic focus areas right now, from news/posts/blog),
slogans_and_phrases (list: taglines, mission statements, recurring phrases the company or its
  hiring managers use publicly - quote them),
recent_news (list: dated where possible),
technical_direction (list: stack choices, architecture moves, engineering practices they talk about),
hiring_goal (2-3 sentences: what problem this hire is meant to solve, read between the lines of the JD),
key_responsibilities (list, 6-10, plain words),
preferred_experience (list: kinds of experience they want, e.g. "shipped payments in a regulated market"),
preferred_knowledge (list: domain knowledge they value),
must_have_skills (list), nice_to_have_skills (list),
tech_stack (list: technologies they use or prefer, most important first),
achievements_wanted (list: the kind of results they would love to see on a resume, concrete),
culture_signals (list: how the team works / values),
competitors (list of objects {{name, what_they_do, difference}} - 3-6 direct competitors and how this
  company differs from each),
partners (list: companion / partner companies or ecosystems they work with and what those do),
ats_keywords (list of 30-45 exact terms, most important first; merge the JD keywords with the
  industry vocabulary an ATS at this company would be configured with),
story_hooks (list of 10-15 realistic, specific work scenarios an engineer at THIS kind of company faces -
  e.g. "reconciling supplier availability cache with a booking engine under peak load", including
  component names, failure modes and production issues engineers actually discuss online. These will
  seed resume bullets, so make them concrete and industry-specific),
plain_summary (object for the UI, short plain-language strings or short lists):
  {{
    "industry": "...",
    "what_they_build": ["...", "..."],
    "projects_now": ["Name – plain-words explanation of what they are building right now", ...],
    "current_focus": ["...", "..."],
    "why_hiring": "...",
    "competitors": ["Name - what they do", ...],
    "partners": ["Name - what they do", ...],
    "tech_they_prefer": ["...", ...],
    "experience_they_want": ["...", ...],
    "achievements_they_want": ["...", ...],
    "phrases_they_use": ["...", ...]
  }},
sources (list of the most useful URLs you relied on).
"""


def _queries(facts: dict) -> list[str]:
    co = facts.get("company_name") or ""
    role = facts.get("role_title") or ""
    site = search.domain_of(facts.get("company_website") or "")
    base = [
        f"{co} company overview products",
        f"{co} what does {co} do customers",
        f"{co} engineering blog architecture tech stack",
        f"{co} news 2026",
        f"{co} mission values slogan",
        f"{co} competitors alternatives",
        f"{co} partnership OR partners OR integration",
        f"{co} hiring {role} team",
        f"{co} linkedin post engineering",
        f"{co} product launch OR roadmap 2026",
    ]
    if site:
        base.append(f"site:{site} about")
        base.append(f"site:{site} careers engineering")
    if config.RESEARCH_DEPTH == "quick":
        base = base[:5]
    return [q for q in base if co]


def analyze_job(jd_url: str, progress: Progress = lambda m: None) -> tuple[str, JDIntel]:
    progress("Fetching the job description page…")
    jd_text = search.fetch_page_text(jd_url)
    if len(jd_text) < 200:
        raise RuntimeError("Could not read the job description from that URL (page too short or blocked). "
                           "Make sure it is public and not behind a login.")

    progress("Extracting role facts from the job description…")
    facts = llm.complete_json(EXTRACT_SYSTEM, EXTRACT_USER.format(jd=jd_text[:45000]),
                              model=config.CLAUDE_FAST_MODEL, max_tokens=6000)
    if not isinstance(facts, dict):
        facts = {}
    if not facts.get("company_name"):
        facts["company_name"] = search.domain_of(jd_url).split(".")[0].title()
    if not facts.get("company_website"):
        facts["company_website"] = ""

    progress(f"Researching {facts['company_name']} on the web (products, focus, news, competitors)…")
    queries = _queries(facts)
    results = search.search_many(queries, max_results=5, depth="advanced")
    # a news-flavoured pass for recency
    news = search.search(f"{facts['company_name']} news", max_results=6, topic="news", days=365)
    results[f"{facts['company_name']} news (news index)"] = news
    digest = search.format_results(results)

    progress("Synthesising the hiring brief…")
    facts_for_llm = {k: v for k, v in facts.items() if k != "jd_clean"}
    facts_for_llm["jd_text"] = facts.get("jd_clean") or jd_text[:6000]
    data = llm.complete_json(SYNTH_SYSTEM, SYNTH_USER.format(facts=json.dumps(facts_for_llm, ensure_ascii=False),
                                                            research=digest[:90000]),
                             model=config.CLAUDE_MODEL, max_tokens=12000)
    # normalise competitor objects
    comps = []
    for c in data.get("competitors", []) or []:
        if isinstance(c, str):
            comps.append({"name": c})
        elif isinstance(c, dict):
            comps.append({"name": c.get("name", ""), "what_they_do": c.get("what_they_do", ""),
                          "difference": c.get("difference", "")})
    data["competitors"] = comps
    for k in ("products", "current_projects", "projects_plain", "current_focus", "slogans_and_phrases", "recent_news",
              "technical_direction", "key_responsibilities", "preferred_experience", "preferred_knowledge",
              "must_have_skills", "nice_to_have_skills", "tech_stack", "achievements_wanted", "culture_signals",
              "partners", "ats_keywords", "story_hooks", "sources"):
        v = data.get(k)
        if v is None:
            data[k] = []
        elif isinstance(v, str):
            data[k] = [v]
        else:
            data[k] = [x if isinstance(x, str) else json.dumps(x, ensure_ascii=False) for x in v]
    # scalar fields must be strings; plain_summary must be a dict
    for k, f in JDIntel.model_fields.items():
        if f.annotation is str and k in data and not isinstance(data[k], str):
            v = data[k]
            data[k] = " ".join(map(str, v)) if isinstance(v, list) else json.dumps(v, ensure_ascii=False)
    if not isinstance(data.get("plain_summary"), dict):
        data["plain_summary"] = {}
    intel = JDIntel(**{k: v for k, v in data.items() if k in JDIntel.model_fields})
    if not intel.role_title:
        intel.role_title = facts.get("role_title", "")
    return facts.get("jd_clean") or jd_text[:8000], intel


COMPANY_SYSTEM = """You write short factual profiles of companies for a resume writer. Only state what the
research supports; if the company is obscure, infer the industry cautiously from its name/site and say
"likely". Include: what they do, industry, products, customers, scale, tech stack hints, and 5-8 concrete
systems/components an engineer there would realistically have worked on (e.g. "driver dispatch service",
"KYC onboarding flow", "odds feed ingestion"). Max 220 words. Plain prose, no headings."""


def research_company(name: str, location: str = "", website: str = "", notes: str = "",
                     progress: Progress = lambda m: None) -> str:
    progress(f"Researching {name}…")
    qs = [f"{name} {location} company".strip(), f"{name} product platform engineering"]
    if website:
        qs.append(f"site:{search.domain_of(website)}")
    results = search.search_many(qs, max_results=4, depth="basic")
    digest = search.format_results(results, limit_per_query=4)
    if website:
        try:
            digest += "\n\n### Company website\n" + search.fetch_page_text(website)[:6000]
        except Exception:
            pass
    user = f"Company: {name}\nLocation: {location}\nWebsite: {website}\nCandidate's own notes: {notes}\n\n" \
           f"<research>\n{digest[:30000]}\n</research>"
    return llm.complete(COMPANY_SYSTEM, user, model=config.CLAUDE_FAST_MODEL, max_tokens=1200)

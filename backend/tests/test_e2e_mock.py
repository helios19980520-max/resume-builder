"""
Offline end-to-end smoke test: no API keys needed.
Mocks the LLM + Tavily layers and drives the real API (jobs, template engine, LibreOffice PDF, ATS).

    cd backend && python -m pytest -q tests/            (or)   python tests/test_e2e_mock.py
"""
from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="rb-test-"))
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("TAVILY_API_KEY", "test")

from fastapi.testclient import TestClient  # noqa: E402

from app import llm, research, search  # noqa: E402
from app.main import app  # noqa: E402
from app.templates.registry import list_templates  # noqa: E402

TEMPLATES = {t.id: t for t in list_templates()}

random.seed(7)

INTEL = {
    "company_name": "12Go", "company_website": "https://12go.asia", "role_title": "Senior Full Stack Engineer",
    "location": "Bangkok / Remote", "employment_type": "Full-time", "seniority": "Senior",
    "industry": "Online travel booking (OTA)", "sub_industry": "Ground transport ticketing",
    "company_summary": "12Go sells train, bus, ferry and flight tickets across Asia.",
    "products": ["12go.asia booking site", "Operator supply API"], "current_projects": ["New checkout"],
    "current_focus": ["Conversion", "Supplier integrations"], "slogans_and_phrases": ["Travel Asia by train, bus, ferry"],
    "recent_news": [], "technical_direction": ["PHP to Node/TypeScript", "PostgreSQL", "Kubernetes"],
    "hiring_goal": "Own the booking flow and payments.", "key_responsibilities": ["Build booking APIs", "Payments"],
    "preferred_experience": ["Marketplace or OTA", "Payments"], "preferred_knowledge": ["PCI basics"],
    "must_have_skills": ["TypeScript", "Node.js", "React", "PostgreSQL"], "nice_to_have_skills": ["Kubernetes", "Redis"],
    "tech_stack": ["TypeScript", "Node.js", "React", "PostgreSQL", "Redis", "Kubernetes", "AWS"],
    "achievements_wanted": ["Cut checkout latency", "Raised conversion"], "culture_signals": ["Small teams"],
    "competitors": [{"name": "Bookaway", "what_they_do": "Ground transport OTA", "difference": "Fewer Asian operators"}],
    "partners": ["Stripe", "Omise"],
    "ats_keywords": ["TypeScript", "Node.js", "React", "PostgreSQL", "Redis", "Kubernetes", "AWS", "REST API",
                     "payments", "booking", "microservices", "CI/CD", "Docker", "GraphQL", "observability"],
    "story_hooks": ["Supplier availability cache going stale during peak season", "Double charge on retry"],
    "plain_summary": {"industry": "Online travel booking", "what_they_build": ["Ticket marketplace"],
                      "current_focus": ["Conversion"], "why_hiring": "Own booking + payments",
                      "competitors": ["Bookaway - ground transport OTA"], "partners": ["Stripe - payments"],
                      "tech_they_prefer": ["TypeScript", "Node.js"], "experience_they_want": ["OTA"],
                      "achievements_they_want": ["Faster checkout"], "phrases_they_use": ["Travel Asia"]},
    "sources": ["https://12go.asia/en/about"],
}

FACTS = {"company_name": "12Go", "company_website": "https://12go.asia", "role_title": "Senior Full Stack Engineer",
         "jd_clean": "Senior Full Stack Engineer at 12Go. TypeScript, Node.js, React, PostgreSQL. " * 20}


def sentence(n: int, kw: str) -> str:
    base = (f"Rewrote the {kw} search path after a stale availability cache kept showing sold-out seats, "
            f"adding a Redis TTL and a PostgreSQL fallback query; p95 fell from 900ms to 300ms and support tickets "
            f"about phantom seats stopped. ")
    s = ""
    while len(s) < n:
        s += base
    return s[:n].rsplit(" ", 1)[0].rstrip(",;") + "."


def make_content(tid: str, profile: dict) -> dict:
    b = TEMPLATES[tid].budget
    n = len(profile["companies"])
    counts = TEMPLATES[tid].bullets_per_company(n)
    kws = INTEL["ats_keywords"]
    exps = []
    for i, c in enumerate(profile["companies"]):
        bullets = []
        for j in range(counts[i]):
            txt = sentence(b.bullet_avg + random.randint(-30, 30), kws[(i + j) % len(kws)])
            if b.bold_keywords:
                txt = txt.replace("search path", "**search path**", 1).replace("stale availability", "**stale availability**", 1)
            bullets.append(txt)
        exps.append({"company": c["name"], "location": c["location"], "remote": c["remote"], "role": c["role_title"] or "Senior Engineer",
                     "start": c["start"], "end": c["end"], "website": c["website"],
                     "company_blurb": sentence(300, "booking") if b.blurb_chars else "",
                     "tech_scope": ("TypeScript, Node.js, React, PostgreSQL, Redis, Kubernetes, AWS, Docker, GitHub Actions, "
                                    "GraphQL, REST API, Jest, Playwright, Stripe, Omise, Grafana, OpenTelemetry"[:b.tech_scope_chars[1]]
                                    if b.tech_scope_chars else ""),
                     "bullets": bullets})
    skills = []
    labels = ["Languages", "Frameworks", "Databases", "Cloud / Infrastructure", "Testing / Observability", "Tools / Practices", "Domain", "Other"]
    for i in range(b.skill_lines):
        items = "TypeScript / Node.js / React / PostgreSQL / Redis / Kubernetes / AWS / Docker / CI/CD"
        items = items[: max(b.skill_line_chars[0], min(b.skill_line_chars[1] - 12, 70 + i * 5))].rsplit(" /", 1)[0]
        skills.append({"label": labels[i] if b.skill_labelled else "", "items": items})
    return {"full_name": profile["full_name"], "headline": "Senior Full Stack Engineer", "location": profile["location"],
            "contact": profile["contact"], "summary": sentence(b.summary_chars, "booking"),
            "skills": skills, "experiences": exps, "education": profile["education"]}


PROFILE = {
    "full_name": "Nam Nguyen", "headline": "", "location": "Hanoi, Vietnam",
    "contact": {"email": "nam@example.com", "phone": "+84 900 000 000", "linkedin": "linkedin.com/in/nam", "github": "", "website": ""},
    "companies": [
        {"name": "Fintos Venture Group", "location": "Malaysia", "remote": True, "role_title": "Senior Full Stack Engineer", "start": "Jan 2024", "end": "Present", "website": "", "notes": ""},
        {"name": "DeliverMe", "location": "Australia", "remote": True, "role_title": "Full Stack Engineer", "start": "Apr 2021", "end": "Dec 2023", "website": "https://www.deliver-me.com.au", "notes": "WebSocket driver tracking"},
        {"name": "foriio", "location": "Japan", "remote": False, "role_title": "Full Stack Developer", "start": "Aug 2017", "end": "Mar 2021", "website": "https://foriio.com", "notes": ""},
    ],
    "education": {"university": "Hanoi University of Science and Technology", "degree": "Bachelor of Science", "field": "Computer Science", "start_year": "2013", "end_year": "2017"},
    "extra_context": "",
}


def install_mocks(tid: str):
    state = {"calls": 0}

    def complete_json(system, user, model=None, max_tokens=0):
        state["calls"] += 1
        if "pull out structured facts" in system:
            return FACTS
        if "hiring brief" in system:
            return INTEL
        if "resume LAYOUT" in system:
            return {"ranking": [{"template_id": t, "score": 90 - i * 10, "reason": "mock"} for i, t in enumerate(TEMPLATES)]}
        # writer / fixer -> well-formed content for the template
        return make_content(tid, PROFILE)

    def complete(system, user, model=None, max_tokens=0, temperature=None):
        return "Fintos Venture Group is a mortgage advisory fintech in Malaysia; engineers work on eKYC onboarding, loan eligibility APIs, advisor dashboards."

    llm.complete_json = complete_json
    llm.complete = complete
    research.llm = llm
    search.fetch_page_text = lambda url: FACTS["jd_clean"]
    search.search = lambda q, **kw: [{"title": "x", "url": "https://12go.asia", "content": "12Go sells tickets", "score": 1}]
    search.search_many = lambda qs, **kw: {q: search.search(q) for q in qs}
    return state


def wait(client: TestClient, job_id: str):
    for _ in range(600):
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] != "running":
            return j
        time.sleep(0.2)
    raise TimeoutError


def run_template(tid: str):
    install_mocks(tid)
    client = TestClient(app)
    assert client.get("/api/health").json()["ok"]
    assert len(client.get("/api/templates").json()) >= 3
    assert client.get("/api/settings").status_code == 200
    r = client.post("/api/sessions", json={"jd_url": "https://12go.asia/en/careers/1"}).json()
    j = wait(client, r["job_id"])
    assert j["status"] == "done", j
    sid = r["session_id"]
    s = client.get(f"/api/sessions/{sid}").json()
    assert s["intel"]["company_name"] == "12Go"
    assert len(s["recommendation"]) == len(TEMPLATES), s["recommendation"]
    assert client.post(f"/api/sessions/{sid}/template", json={"template_id": tid}).json()["template_id"] == tid

    r = client.post(f"/api/sessions/{sid}/generate", json={"profile": PROFILE}).json()
    j = wait(client, r["job_id"])
    assert j["status"] == "done", j
    s = client.get(f"/api/sessions/{sid}").json()
    ats = s["ats"]
    assert ats["total"] > 60, ats
    assert j["result"]["pages"] in (2, 3, 4), j["result"]
    assert client.get(f"/api/sessions/{sid}/download/docx").status_code == 200
    assert client.get(f"/api/sessions/{sid}/download/pdf").status_code == 200

    r = client.post(f"/api/sessions/{sid}/revise", json={"feedback": "shorter summary"}).json()
    j = wait(client, r["job_id"])
    assert j["status"] == "done", j
    s = client.get(f"/api/sessions/{sid}").json()
    assert s["version"] == 2
    assert client.post(f"/api/sessions/{sid}/complete").json()["ok"]
    print(f"[{tid}] ATS {ats['total']} ({ats['grade']}), pages {j['result']['pages']}, "
          f"checks: " + ", ".join(f"{c['name']} {c['score']}/{c['max_score']}" for c in ats["checks"]))
    return sid


def test_all_templates():
    for tid in TEMPLATES:
        run_template(tid)


if __name__ == "__main__":
    for tid in TEMPLATES:
        run_template(tid)
    print("data dir:", os.environ["DATA_DIR"])

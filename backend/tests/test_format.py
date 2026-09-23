"""Location formatting and bullet-sentence cleanup. No API keys."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.humanize import drop_em_dashes, find_flags
from app.models import Experience, ResumeContent
from app.templates.generic import _vars_exp, display_location, pattern_segments, pattern_text
from app.writer import _style_problems


def _exp(**kw) -> Experience:
    base = dict(company="T/DG", location="US", remote=True, role="Engineer", start="2024", end="Present",
                bullets=["Kept the payments API up during the Stripe cutover."])
    base.update(kw)
    return Experience(**base)


def test_remote_sits_on_the_right_of_the_location():
    assert display_location("US", True) == "US, Remote"
    assert display_location("Japan", True) == "Japan, Remote"
    assert display_location("US", False) == "US"
    assert display_location("", True) == "Remote"
    assert display_location("Germany, Remote", True) == "Germany, Remote"
    assert display_location("Japan, Hybrid", False) == "Japan, Hybrid"


def test_doi_header_prints_location_with_remote():
    e = _exp()
    vals = {"role": "Senior GPU Engineer", "company": "BeamNG", "location": "Germany, Remote", "dates": "2024 – Present"}
    text = pattern_text("{role} | [{company}]\n[{location}] | [{dates}]", vals, _vars_exp(e, vals))
    assert text == "Engineer | [T/DG]\n[US, Remote] | [2024 – Present]"


def test_daniel_header_does_not_repeat_remote():
    e = _exp(company="Neural Internet", location="US", remote=True)
    vals = {"company": "Neural Internet", "location": "US", "remote": "Remote"}
    text = pattern_text("{company} ({location}) {remote}", vals, _vars_exp(e, vals))
    assert text == "Neural Internet (US, Remote)"

    off = _exp(company="Neural Internet", location="US", remote=False)
    assert pattern_text("{company} ({location}) {remote}", vals, _vars_exp(off, vals)) == "Neural Internet (US)"


def test_daniel_header_keeps_the_date_separator_when_remote_is_folded():
    e = _exp(company="Co", location="Switzerland", remote=True, start="2020", end="2022")
    vals = {"company": "Co", "location": "Switzerland", "remote": "Remote", "start": "03/2024", "end": "Present"}
    text = pattern_text("{company} ({location}) {remote} – {start} to {end}", vals, _vars_exp(e, vals))
    assert text == "Co (Switzerland, Remote) – 2020 to 2022"


def test_an_empty_only_placeholder_does_not_print_the_token():
    assert pattern_text("{remote}", {}, {"remote": ""}) == ""
    assert pattern_segments(None, "{remote}", {}, {"remote": ""}) == []
    assert pattern_text("Kept as-is", {}, {}) == "Kept as-is"
    e = _exp(company="Co", location="", remote=False)
    vals = {"company": "Co", "location": "US"}
    assert pattern_text("{company} ({location})", vals, _vars_exp(e, vals)) == "Co"


def test_empty_contact_field_drops_its_separator():
    assert pattern_text("{location} | {email} | {phone}", {}, {"location": "Hanoi", "email": "a@b.c", "phone": ""}) == "Hanoi | a@b.c"
    assert pattern_text("{phone} | {email}", {}, {"phone": "", "email": "a@b.c"}) == "a@b.c"


def test_em_dash_aside_becomes_a_normal_clause():
    src = ("Slasify is a Singapore-based HR tech company doing Employer of Record, global payroll and "
           "contractor payments across 150+ countries and 130+ currencies. I worked on the payroll engine "
           "and the client dashboard, and over time took most of the production support for payout failures "
           "— the part of the month where money has to land on time.")
    out = drop_em_dashes(src)
    assert "—" not in out
    assert "payout failures. That is the part of the month where money has to land on time." in out
    assert "Singapore-based" in out
    assert "150+" in out
    clause = drop_em_dashes("Retries were not idempotent — a second payout ran for the same contractor.")
    assert clause == "Retries were not idempotent. A second payout ran for the same contractor."
    flags = find_flags(src)
    assert any("em dash" in f for f in flags)
    assert not any("em dash" in f for f in find_flags(out))
    assert drop_em_dashes("Built the multi-currency disbursement service.") == "Built the multi-currency disbursement service."
    assert drop_em_dashes("2020 – 2024") == "2020 – 2024"


def _content(bullets: list[str], blurb: str = "") -> ResumeContent:
    return ResumeContent(
        full_name="A", headline="E", location="Hanoi",
        contact={"email": "a@b.c"}, summary="I build payment services.", skills=[],
        experiences=[_exp(bullets=bullets, company_blurb=blurb)],
        education={"university": "U", "degree": "B", "field": "CS", "start_year": "2013", "end_year": "2017"},
    )


def test_em_dash_in_a_blurb_is_flagged():
    problems = _style_problems(_content(
        ["Built and maintained the multi-currency disbursement service in Node.js and TypeScript."],
        blurb="I took most of the production support for payout failures — the part of the month where money has to land on time.",
    ))
    assert any("company_blurb" in p and "em dash" in p for p in problems)
    clean = _style_problems(_content(
        ["Built and maintained the multi-currency disbursement service in Node.js and TypeScript."],
        blurb="I took most of the production support for payout failures, the part of the month where money has to land on time.",
    ))
    assert not any("em dash" in p for p in clean)

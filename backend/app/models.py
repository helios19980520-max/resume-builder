from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl

TemplateId = str


# ------------------------------------------------------------------ inputs
class AnalyzeRequest(BaseModel):
    jd_url: str
    template_id: str = ""  # optional; normally chosen after the analysis


class SelectTemplateRequest(BaseModel):
    template_id: str


class SettingsRequest(BaseModel):
    ANTHROPIC_API_KEY: Optional[str] = None
    TAVILY_API_KEY: Optional[str] = None
    CLAUDE_MODEL: Optional[str] = None
    CLAUDE_FAST_MODEL: Optional[str] = None


class TemplateScore(BaseModel):
    template_id: str
    score: int
    reason: str


class Contact(BaseModel):
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""


class CompanyInput(BaseModel):
    name: str
    location: str = ""  # "Malaysia", "US"
    remote: bool = False
    role_title: str = ""  # optional; generated if empty
    start: str  # free text like "Jan 2024" or "03/2024"
    end: str = "Present"
    website: str = ""
    notes: str = ""  # optional hints / things to highlight


class EducationInput(BaseModel):
    university: str
    degree: str = "Bachelor of Science"
    field: str = "Computer Science"
    start_year: str = ""
    end_year: str = ""


class ProfileInput(BaseModel):
    full_name: str
    headline: str = ""  # e.g. "Senior Full Stack Engineer" (defaults to JD title)
    location: str
    contact: Contact = Contact()
    companies: list[CompanyInput]
    education: EducationInput
    extra_context: str = ""


class GenerateRequest(BaseModel):
    profile: ProfileInput


class ReviseRequest(BaseModel):
    feedback: str


# ------------------------------------------------------------------ research output
class CompetitorInfo(BaseModel):
    name: str
    what_they_do: str = ""
    difference: str = ""


class JDIntel(BaseModel):
    company_name: str = ""
    company_website: str = ""
    role_title: str = ""
    location: str = ""
    employment_type: str = ""
    seniority: str = ""
    industry: str = ""
    sub_industry: str = ""
    company_summary: str = ""
    products: list[str] = []
    current_projects: list[str] = []
    projects_plain: list[str] = []
    current_focus: list[str] = []
    slogans_and_phrases: list[str] = []
    recent_news: list[str] = []
    technical_direction: list[str] = []
    hiring_goal: str = ""  # what they want to solve with this hire
    key_responsibilities: list[str] = []
    preferred_experience: list[str] = []
    preferred_knowledge: list[str] = []
    must_have_skills: list[str] = []
    nice_to_have_skills: list[str] = []
    tech_stack: list[str] = []
    achievements_wanted: list[str] = []
    culture_signals: list[str] = []
    competitors: list[CompetitorInfo] = []
    partners: list[str] = []
    ats_keywords: list[str] = []  # ranked, most important first
    story_hooks: list[str] = []  # realistic scenarios we can echo in bullets
    plain_summary: dict[str, Any] = {}  # what the UI shows
    sources: list[str] = []


# ------------------------------------------------------------------ resume content
class SkillLine(BaseModel):
    label: str = ""  # only used by templates with labelled lines (doi)
    items: str


class Experience(BaseModel):
    company: str
    location: str = ""
    remote: bool = False
    role: str
    start: str
    end: str
    website: str = ""
    company_blurb: str = ""  # doi template: italic one-paragraph company description
    tech_scope: str = ""  # nam / daniel: "Technical Scope:" line content (without label)
    bullets: list[str]  # may contain **bold** markers (daniel)


class Education(BaseModel):
    university: str
    degree: str
    field: str
    start_year: str = ""
    end_year: str = ""


class ResumeContent(BaseModel):
    full_name: str
    headline: str
    location: str
    contact: Contact
    summary: str
    skills: list[SkillLine]
    experiences: list[Experience]
    education: Education


# ------------------------------------------------------------------ ATS
class ATSCheck(BaseModel):
    name: str
    score: float
    max_score: float
    detail: str
    items: list[str] = []


class ATSReport(BaseModel):
    total: float
    grade: str
    checks: list[ATSCheck]
    matched_keywords: list[str]
    missing_keywords: list[str]
    flagged_phrases: list[str]
    length_report: dict[str, Any]


# ------------------------------------------------------------------ session
class SessionState(BaseModel):
    id: str
    template_id: str = ""
    jd_url: str
    recommendation: list[TemplateScore] = []
    jd_text: str = ""
    intel: Optional[JDIntel] = None
    profile: Optional[ProfileInput] = None
    company_profiles: dict[str, str] = {}
    content: Optional[ResumeContent] = None
    ats: Optional[ATSReport] = None
    version: int = 0
    history: list[dict[str, Any]] = []
    status: str = "new"

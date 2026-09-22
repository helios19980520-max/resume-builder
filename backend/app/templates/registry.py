"""
Template library.

Every template = one folder under DATA_DIR/templates/<id>/ holding
    template.docx   the original file (never modified)
    map.json        the TemplateMap produced by analyzer.py
    preview.png     first-page thumbnail (when a renderer is available)
Built-in templates ship in app/templates/builtin/ (docx + pre-computed map + preview) and are copied
into the library on first start, so they follow exactly the same code path as uploaded ones.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import uuid
from dataclasses import dataclass

from .. import config
from ..models import ResumeContent
from . import analyzer
from .engine import TemplateDoc
from .generic import GenericTemplate

log = logging.getLogger("templates")

HERE = os.path.dirname(__file__)
BUILTIN = os.path.join(HERE, "builtin")


def library_dir() -> str:
    d = os.path.join(config.DATA_DIR, "templates")
    os.makedirs(d, exist_ok=True)
    return d


@dataclass
class Budget:
    summary_chars: int
    summary_tolerance: float
    skill_lines: int
    skill_line_chars: tuple[int, int]
    skill_labelled: bool
    total_bullets: int
    bullet_chars: tuple[int, int]
    bullet_avg: int
    tech_scope_chars: tuple[int, int] | None
    blurb_chars: tuple[int, int] | None
    voice: str
    bold_keywords: bool
    bullets_per_job_original: list[int] | None = None


class TemplateSpec:
    def __init__(self, folder: str):
        self.folder = folder
        with open(os.path.join(folder, "map.json"), encoding="utf-8") as f:
            self.map = json.load(f)
        for p in self.map.get("paragraphs", []) + self.map.get("textbox_paragraphs", []):
            p["values"] = {str(k).strip("{} "): v for k, v in (p.get("values") or {}).items()}
        b = self.map["budget"]
        self.budget = Budget(
            summary_chars=b["summary_chars"], summary_tolerance=b.get("summary_tolerance", 0.08),
            skill_lines=b["skill_lines"], skill_line_chars=tuple(b["skill_line_chars"]),
            skill_labelled=b["skill_labelled"], total_bullets=b["total_bullets"],
            bullet_chars=tuple(b["bullet_chars"]), bullet_avg=b["bullet_avg"],
            tech_scope_chars=tuple(b["tech_scope_chars"]) if b.get("tech_scope_chars") else None,
            blurb_chars=tuple(b["blurb_chars"]) if b.get("blurb_chars") else None,
            voice=b["voice"], bold_keywords=b["bold_keywords"],
            bullets_per_job_original=b.get("bullets_per_job_original"),
        )
        self.id = self.map["id"]
        self.name = self.map.get("name") or self.id
        self.description = self.map.get("description") or ""
        self.style_summary = self.map.get("style_summary") or ""
        self.tone = self.map.get("tone") or ""
        self.best_for = self.map.get("best_for") or []
        self.features = self.map.get("features") or {}
        self.builtin = bool(self.map.get("builtin"))
        pg = self.map.get("page") or {}
        self.page = (f"{pg.get('width_in')}×{pg.get('height_in')} in, margins " +
                     "/".join(str(m) for m in (pg.get("margins_in") or []))) if pg else ""
        fonts = self.map.get("fonts") or {}
        names = list(dict.fromkeys([fonts.get("theme_major", ""), fonts.get("theme_minor", "")] + list((fonts.get("explicit") or {}).keys())))
        self.fonts = ", ".join(n for n in names if n)[:120]

    def path(self) -> str:
        return os.path.join(self.folder, "template.docx")

    def preview_path(self) -> str | None:
        p = os.path.join(self.folder, "preview.png")
        return p if os.path.exists(p) else None

    def bullets_per_company(self, n: int) -> list[int]:
        """Distribute the template's bullet count over n companies, recent-first weighted."""
        if n <= 0:
            return []
        orig = self.budget.bullets_per_job_original or []
        if orig and len(orig) == n:
            return [min(12, max(3, x)) for x in orig]
        weights = [1.35] + [1.0] * (n - 1)
        if n >= 3:
            weights[-1] = 0.8
        total = self.budget.total_bullets
        raw = [total * w / sum(weights) for w in weights]
        return [min(12, max(3, round(x))) for x in raw]

    def compose(self, td: TemplateDoc, content: ResumeContent):
        GenericTemplate(json.loads(json.dumps(self.map)), self.path()).compose(td, content)

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "description": self.description, "style_summary": self.style_summary,
                "tone": self.tone, "best_for": self.best_for, "page": self.page, "fonts": self.fonts,
                "builtin": self.builtin, "source_name": self.map.get("source_name", ""),
                "has_preview": self.preview_path() is not None,
                "preview_url": f"/api/templates/{self.id}/preview",
                "budget": {"summary_chars": self.budget.summary_chars, "skill_lines": self.budget.skill_lines,
                           "total_bullets": self.budget.total_bullets, "bullet_chars": list(self.budget.bullet_chars),
                           "bold_keywords": self.budget.bold_keywords, "labelled_skills": self.budget.skill_labelled},
                "features": self.features}


# --------------------------------------------------------------------------- library ops
def seed_builtins() -> None:
    lib = library_dir()
    if not os.path.isdir(BUILTIN):
        return
    for name in sorted(os.listdir(BUILTIN)):
        src = os.path.join(BUILTIN, name)
        if not os.path.isdir(src) or not os.path.exists(os.path.join(src, "map.json")):
            continue
        dst = os.path.join(lib, name)
        dst_map = os.path.join(dst, "map.json")
        if os.path.exists(dst_map):
            try:
                with open(os.path.join(src, "map.json"), encoding="utf-8") as f:
                    new_v = json.load(f).get("map_version", 0)
                with open(dst_map, encoding="utf-8") as f:
                    old_v = json.load(f).get("map_version", 0)
            except Exception:
                new_v, old_v = 1, 0
            if new_v <= old_v:
                continue
            log.info("updating built-in template %s (map v%s -> v%s)", name, old_v, new_v)
        shutil.copytree(src, dst, dirs_exist_ok=True)
        log.info("seeded built-in template %s", name)


def list_templates() -> list[TemplateSpec]:
    seed_builtins()
    out = []
    for name in sorted(os.listdir(library_dir())):
        folder = os.path.join(library_dir(), name)
        if os.path.exists(os.path.join(folder, "map.json")):
            try:
                out.append(TemplateSpec(folder))
            except Exception as e:  # corrupt entry: skip, don't kill the list
                log.warning("skipping template %s: %s", name, e)
    # built-ins first, then by name
    out.sort(key=lambda t: (not t.builtin, t.name.lower()))
    return out


def get_template(tid: str) -> TemplateSpec:
    seed_builtins()
    folder = os.path.join(library_dir(), tid)
    if not os.path.exists(os.path.join(folder, "map.json")):
        raise KeyError(f"unknown template {tid}")
    return TemplateSpec(folder)


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", os.path.splitext(name)[0].lower()).strip("-")[:32] or "template"
    return f"{base}-{uuid.uuid4().hex[:6]}"


def add_template(docx_bytes: bytes, filename: str, make_preview=None) -> TemplateSpec:
    """Analyse an uploaded .docx and add it to the library. `make_preview(docx_path, png_path)` optional."""
    tid = _slug(filename)
    folder = os.path.join(library_dir(), tid)
    os.makedirs(folder, exist_ok=True)
    docx_path = os.path.join(folder, "template.docx")
    with open(docx_path, "wb") as f:
        f.write(docx_bytes)
    try:
        tmap = analyzer.analyze_docx(docx_path, tid, filename)
        tmap["builtin"] = False
        # dry-run render to make sure the map is usable before we accept it
        from ..models import Contact, Education, Experience, SkillLine
        probe = ResumeContent(full_name="Probe Person", headline="Engineer", location="City", contact=Contact(email="p@x.io"),
                              summary="probe " * 40, skills=[SkillLine(label="Skills", items="a / b / c")] * tmap["budget"]["skill_lines"],
                              experiences=[Experience(company="Co", location="US", remote=True, role="Dev", start="2020", end="2021",
                                                      tech_scope="a, b", company_blurb="blurb", website="https://x.io", bullets=["one **two** three"] * 3)],
                              education=Education(university="U", degree="BSc", field="CS", start_year="2010", end_year="2014"))
        from .generic import render_generic
        render_generic(tmap, docx_path, probe, os.path.join(folder, "_probe.docx"))
        os.remove(os.path.join(folder, "_probe.docx"))
        with open(os.path.join(folder, "map.json"), "w", encoding="utf-8") as f:
            json.dump(tmap, f, ensure_ascii=False, indent=1)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    if make_preview:
        try:
            make_preview(docx_path, os.path.join(folder, "preview.png"))
        except Exception as e:
            log.warning("preview failed for %s: %s", tid, e)
    return TemplateSpec(folder)


def delete_template(tid: str) -> None:
    folder = os.path.join(library_dir(), tid)
    if os.path.isdir(folder):
        shutil.rmtree(folder)


def render_docx(tid: str, content: ResumeContent, out_path: str) -> str:
    spec = get_template(tid)
    td = TemplateDoc(spec.path())
    spec.compose(td, content)
    td.save(out_path)
    return out_path

from __future__ import annotations

import html
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import ats, config, jobs, recommend, research, storage, writer
from .models import (AnalyzeRequest, GenerateRequest, ReviseRequest, SelectTemplateRequest, SessionState,
                     SettingsRequest)
from .render import RenderUnavailable, capabilities, docx_preview_png, docx_to_pdf, pdf_pages
from .templates.analyzer import TemplateError
from .humanize import drop_em_dashes
from .templates.engine import strip_md, visible_text
from .templates.generic import display_location
from .templates.registry import add_template, delete_template, get_template, list_templates, render_docx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("api")

app = FastAPI(title="Resume Builder API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _load_or_404(sid: str) -> SessionState:
    try:
        return storage.load(sid)
    except KeyError:
        raise HTTPException(404, "session not found")


# --------------------------------------------------------------------------- meta / settings
@app.get("/api/health")
def health():
    return {"ok": True, "missing_keys": config.missing_keys(), "model": config.model(), "fast_model": config.fast_model(),
            "render": capabilities(), "key_sources": config.key_sources(), "data_dir": config.DATA_DIR,
            "desktop": bool(getattr(sys, "frozen", False))}


@app.get("/api/settings")
def get_settings():
    def masked(v: str) -> str:
        return (v[:10] + "…" + v[-4:]) if len(v) > 16 else ("set" if v else "")
    return {"ANTHROPIC_API_KEY": masked(config.anthropic_key()), "TAVILY_API_KEY": masked(config.tavily_key()),
            "CLAUDE_MODEL": config.model(), "CLAUDE_FAST_MODEL": config.fast_model(), "sources": config.key_sources()}


@app.post("/api/settings")
def set_settings(req: SettingsRequest):
    config.save_settings(req.model_dump())
    return get_settings()


# --------------------------------------------------------------------------- templates
@app.get("/api/templates")
def templates():
    return [t.public() for t in list_templates()]


@app.get("/api/templates/{tid}/preview")
def template_preview(tid: str):
    try:
        p = get_template(tid).preview_path()
    except KeyError:
        raise HTTPException(404)
    if not p:
        raise HTTPException(404, "no preview")
    return FileResponse(p, media_type="image/png")


@app.post("/api/templates")
async def upload_template(file: UploadFile = File(...)):
    if missing := config.missing_keys():
        raise HTTPException(400, f"Missing API keys: {', '.join(missing)}. Open Settings.")
    name = file.filename or "template.docx"
    if not name.lower().endswith(".docx"):
        raise HTTPException(400, "Please upload a .docx file (Word). PDFs cannot be used as templates.")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(400, "File too large (15 MB max)")

    def run(job: jobs.Job):
        job.progress(f"Reading {name}…")
        job.progress("Analysing layout, fonts and sections with the model…")

        def preview(docx_path, png_path):
            job.progress("Rendering thumbnail…")
            docx_preview_png(docx_path, png_path)

        try:
            spec = add_template(data, name, make_preview=preview)
        except TemplateError as e:
            raise RuntimeError(str(e))
        job.progress(f"Added template “{spec.name}”.")
        return {"template": spec.public()}

    job = jobs.start("template", run)
    return {"job_id": job.id}


@app.delete("/api/templates/{tid}")
def remove_template(tid: str):
    try:
        spec = get_template(tid)
    except KeyError:
        raise HTTPException(404)
    if spec.builtin:
        raise HTTPException(400, "Built-in templates cannot be deleted")
    delete_template(tid)
    return {"ok": True}


# --------------------------------------------------------------------------- jobs
@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return j.to_dict()


# --------------------------------------------------------------------------- step 1: analyze (+ recommend)
@app.post("/api/sessions")
def create_session(req: AnalyzeRequest):
    if missing := config.missing_keys():
        raise HTTPException(400, f"Missing API keys: {', '.join(missing)}. Open Settings and add them.")
    if not re.match(r"^https?://", req.jd_url.strip()):
        raise HTTPException(400, "Job description link must be a public http(s) URL")
    if req.template_id:
        get_template(req.template_id)
    state = SessionState(id=storage.new_id(), template_id=req.template_id, jd_url=req.jd_url.strip(), status="analyzing")
    storage.save(state)

    def run(job: jobs.Job):
        jd_text, intel = research.analyze_job(state.jd_url, job.progress)
        st = storage.load(state.id)
        st.jd_text = jd_text
        st.intel = intel
        job.progress("Ranking your templates for this job…")
        st.recommendation = recommend.rank_templates(intel, list_templates())
        if not st.template_id and st.recommendation:
            st.template_id = st.recommendation[0].template_id
        st.status = "analyzed"
        storage.save(st)
        job.progress("Analysis complete.")
        return {"session_id": st.id}

    job = jobs.start("analyze", run)
    return {"session_id": state.id, "job_id": job.id}


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    st = _load_or_404(sid)
    d = st.model_dump()
    d.pop("jd_text", None)
    return d


@app.post("/api/sessions/{sid}/template")
def select_template(sid: str, req: SelectTemplateRequest):
    st = _load_or_404(sid)
    try:
        get_template(req.template_id)
    except KeyError:
        raise HTTPException(404, "template not found")
    st.template_id = req.template_id
    storage.save(st)
    return {"ok": True, "template_id": st.template_id}


# --------------------------------------------------------------------------- step 3/4: generate / revise
def _build_files(st: SessionState, job: jobs.Job):
    spec = get_template(st.template_id)
    st.version += 1
    docx_path, _ = storage.version_paths(st.id, st.version)
    job.progress("Filling the Word template…")
    render_docx(st.template_id, st.content, docx_path)
    pages = 0
    pdf_ok = True
    try:
        job.progress("Rendering PDF preview…")
        pdf_path = docx_to_pdf(docx_path, os.path.dirname(docx_path))
        pages = pdf_pages(pdf_path)
    except RenderUnavailable as e:
        pdf_ok = False
        job.progress("No PDF converter found on this machine – the .docx is ready, preview is approximate. " + str(e))
    job.progress("Running ATS self-check…")
    st.ats = ats.score(spec, st.intel, st.content, visible_text(docx_path))
    st.history.append({"version": st.version, "ats": st.ats.total, "pages": pages, "pdf": pdf_ok})
    st.status = "generated"
    storage.save(st)
    return {"session_id": st.id, "version": st.version, "pages": pages, "ats_total": st.ats.total, "pdf": pdf_ok}


@app.post("/api/sessions/{sid}/generate")
def generate(sid: str, req: GenerateRequest):
    st = _load_or_404(sid)
    if not st.intel:
        raise HTTPException(400, "Run the analysis first")
    if not st.template_id:
        raise HTTPException(400, "Choose a template first")
    if not req.profile.companies:
        raise HTTPException(400, "Add at least one company")
    st.profile = req.profile
    if not st.profile.headline:
        st.profile.headline = st.intel.role_title or "Software Engineer"
    st.status = "generating"
    storage.save(st)

    def run(job: jobs.Job):
        s = storage.load(sid)
        spec = get_template(s.template_id)
        job.progress(f"Researching {len(s.profile.companies)} past employer(s)…")
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {c.name: ex.submit(research.research_company, c.name, c.location, c.website, c.notes)
                    for c in s.profile.companies if c.name not in s.company_profiles}
            for name, f in futs.items():
                try:
                    s.company_profiles[name] = f.result()
                except Exception as e:
                    log.warning("company research failed for %s: %s", name, e)
                    s.company_profiles[name] = f"{name}: no public information found; write generically for its industry."
        storage.save(s)
        s.content = writer.write_resume(spec, s.intel, s.profile, s.company_profiles, job.progress)
        return _build_files(s, job)

    job = jobs.start("generate", run)
    return {"job_id": job.id}


@app.post("/api/sessions/{sid}/revise")
def revise(sid: str, req: ReviseRequest):
    st = _load_or_404(sid)
    if not st.content:
        raise HTTPException(400, "Generate a resume first")
    if not req.feedback.strip():
        raise HTTPException(400, "Feedback is empty")

    def run(job: jobs.Job):
        s = storage.load(sid)
        spec = get_template(s.template_id)
        s.content = writer.revise_resume(spec, s.intel, s.profile, s.company_profiles, s.content, req.feedback, job.progress)
        s.history.append({"feedback": req.feedback})
        return _build_files(s, job)

    job = jobs.start("revise", run)
    return {"job_id": job.id}


@app.post("/api/sessions/{sid}/complete")
def complete(sid: str):
    st = _load_or_404(sid)
    st.status = "complete"
    storage.save(st)
    return {"ok": True, "docx": f"/api/sessions/{sid}/download/docx", "pdf": f"/api/sessions/{sid}/download/pdf"}


# --------------------------------------------------------------------------- files / previews
def _safe_name(st: SessionState, ext: str) -> str:
    name = st.profile.full_name if st.profile else "resume"
    role = (st.intel.role_title if st.intel else "") or ""
    co = (st.intel.company_name if st.intel else "") or ""
    base = " - ".join(x for x in (name, role, co) if x)
    base = re.sub(r"[^\w\- .()]", "", base).strip() or "resume"
    return f"{base}.{ext}"


@app.get("/api/sessions/{sid}/preview.pdf")
def preview_pdf(sid: str, v: int | None = None):
    st = _load_or_404(sid)
    _, pdf = storage.version_paths(sid, v or st.version)
    if not os.path.exists(pdf):
        raise HTTPException(404, "no PDF for this version")
    return FileResponse(pdf, media_type="application/pdf", headers={"Cache-Control": "no-store"})


@app.get("/api/sessions/{sid}/preview.html", response_class=HTMLResponse)
def preview_html(sid: str):
    """Approximate preview used when no PDF converter exists on the machine."""
    st = _load_or_404(sid)
    if not st.content:
        raise HTTPException(404)
    c = st.content
    e = html.escape

    def md(s: str) -> str:
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", e(s))
    parts = [f"<h1>{e(c.full_name)}</h1><div class='sub'>{e(c.headline)}</div>",
             f"<div class='sub'>{e(' | '.join(x for x in (c.location, c.contact.email, c.contact.phone, c.contact.linkedin) if x))}</div>",
             f"<h2>Summary</h2><p>{e(strip_md(drop_em_dashes(c.summary)))}</p>", "<h2>Skills</h2><ul>"]
    parts += [f"<li>{('<b>' + e(s.label) + ':</b> ') if s.label else ''}{e(s.items)}</li>" for s in c.skills]
    parts.append("</ul><h2>Experience</h2>")
    for x in c.experiences:
        loc = display_location(x.location, x.remote)
        parts.append(f"<h3>{e(x.role)} · {e(x.company)}{(' (' + e(loc) + ')') if loc else ''} <span>{e(x.start)} – {e(x.end)}</span></h3>")
        if x.company_blurb:
            parts.append(f"<p class='blurb'>{e(drop_em_dashes(x.company_blurb))}</p>")
        if x.tech_scope:
            parts.append(f"<p class='scope'><b>Technical Scope:</b> {e(x.tech_scope)}</p>")
        parts.append("<ul>" + "".join(f"<li>{md(drop_em_dashes(b))}</li>" for b in x.bullets) + "</ul>")
    ed = c.education
    parts.append(f"<h2>Education</h2><p><b>{e(ed.university)}</b><br>{e(ed.degree)} in {e(ed.field)} {e(ed.start_year)}{' – ' if ed.start_year and ed.end_year else ''}{e(ed.end_year)}</p>")
    css = ("body{font-family:Cambria,Georgia,serif;max-width:780px;margin:24px auto;padding:0 20px;color:#222;line-height:1.45}"
           "h1{margin:0;font-size:26px}h2{font-size:15px;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid #999;margin-top:22px}"
           "h3{font-size:14px;margin:14px 0 4px}h3 span{float:right;font-weight:normal;color:#555}.sub{color:#555;font-size:13px}"
           ".blurb{font-style:italic;color:#444}.scope{font-size:13px}li{margin:3px 0;font-size:13.5px}"
           ".note{background:#fff7e0;border:1px solid #f0d58a;padding:8px 12px;border-radius:6px;font-size:13px;margin-bottom:16px}")
    note = "<div class='note'>Approximate preview: no PDF converter (Word or LibreOffice) was found on this computer. The downloaded .docx keeps the template's exact formatting.</div>"
    return f"<!doctype html><meta charset='utf-8'><style>{css}</style>{note}{''.join(parts)}"


@app.get("/api/sessions/{sid}/download/{kind}")
def download(sid: str, kind: str, v: int | None = None):
    st = _load_or_404(sid)
    docx_path, pdf_path = storage.version_paths(sid, v or st.version)
    path = {"docx": docx_path, "pdf": pdf_path}.get(kind)
    if not path:
        raise HTTPException(404)
    if not os.path.exists(path):
        raise HTTPException(404, "file not generated yet" if kind == "docx" else "no PDF (no converter on this machine)")
    media = ("application/vnd.openxmlformats-officedocument.wordprocessingml.document" if kind == "docx" else "application/pdf")
    return FileResponse(path, filename=_safe_name(st, kind), media_type=media)


@app.exception_handler(Exception)
async def unhandled(_, exc: Exception):
    log.exception("unhandled")
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


# --------------------------------------------------------------------------- static frontend (desktop build / single-process mode)
def _static_dir() -> str | None:
    cands = []
    if getattr(sys, "frozen", False):
        cands.append(os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "static"))
        cands.append(os.path.join(os.path.dirname(sys.executable), "static"))
    cands.append(os.getenv("STATIC_DIR", ""))
    cands.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "static"))
    for c in cands:
        if c and os.path.exists(os.path.join(c, "index.html")):
            return c
    return None


_static = _static_dir()
if _static:
    app.mount("/", StaticFiles(directory=_static, html=True), name="static")

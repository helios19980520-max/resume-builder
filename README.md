# Resume Builder

Turns a public job-description link + any Word resume template + your career facts into a tailored resume
(DOCX + PDF) that keeps the template's exact layout, reads like a person wrote it, and comes with a
self-computed ATS score.

```
1. jd link            ->  research company & role  ->  plain-language brief incl. "projects they build now"
2. template library   ->  every template ranked for THIS job (recommended one pre-selected)
3. your facts         ->  name, contacts, companies + dates + notes, university
4. write              ->  research each employer -> draft -> mechanical checks -> fill template -> PDF -> ATS
   feedback loop      ->  regenerate  ->  Complete -> download .docx (+ .pdf)
```

## Ways to run it

| | How | Best for |
|---|---|---|
| **Desktop (.exe)** | `build_exe.bat` once on a Windows PC → `dist\ResumeBuilder.exe` | sharing with people who should not run servers |
| **Docker Compose** | `docker compose up --build` → http://localhost:3000 | a shared server (see §6 for the deploy script) |
| **Dev** | `uvicorn app.main:app --reload` + `npm run dev` | changing the code |

### Desktop build (what the .exe is)
One executable that starts the API, serves the web UI and opens your browser. Data (templates you upload,
sessions, generated files, settings) lives in `%LOCALAPPDATA%\ResumeBuilder\data`. API keys from `.env` are
baked in as defaults by the build; the **Settings** screen (⚙) can override them per machine.

Build steps on Windows (needs Python 3.11/3.12 with "Add to PATH" and Node.js 18+):

```bat
build_exe.bat
```
Output: `dist\ResumeBuilder.exe` (~120 MB, single file). Double-click to run; a small console window stays
open — closing it quits the app. Alternatively push the repo to GitHub with secrets `ANTHROPIC_API_KEY` /
`TAVILY_API_KEY` and run the **build-windows-exe** workflow; the .exe appears as a downloadable artifact.

PDF previews/downloads on the desktop use **Microsoft Word** if installed (identical to Word), else
**LibreOffice** if installed, else the app produces the .docx only and shows an approximate preview.

## Keys

| Key | Where | Used for |
|---|---|---|
| `ANTHROPIC_API_KEY` | https://platform.claude.com/ | template analysis, JD extraction, research synthesis, ranking, writing |
| `TAVILY_API_KEY` | https://app.tavily.com/ | web search + page extraction (JD page, company research) |

Precedence: Settings screen → environment / `.env` → keys baked into the desktop build.
Default models: `claude-opus-5` (synthesis, template analysis, writing) and `claude-sonnet-5` (extraction,
employer profiles, ranking, later fix passes) — both changeable in Settings or `.env`.

## Templates: upload any .docx

The library starts with three built-ins and grows with every upload. An uploaded Word resume is analysed
once (`backend/app/templates/analyzer.py`):

1. **Inventory** – every paragraph (incl. text boxes) with style, size, bold/italic/caps, numbering, tab runs,
   line breaks, indents; page size, margins, fonts.
2. **Classification** – the model labels each paragraph with a role (name, contact, headings, summary, skill
   line, job header lines, tech-scope, employer blurb, bullet, url, education, blank, static, drawing) and,
   for header-like lines, a *pattern* such as `{company} ({location})\t{dates}` plus the original values.
3. **Map + budgets** – the job block structure is learned from the first job; lengths (summary chars, skill
   lines, bullets per job, chars per bullet, tech-scope/blurb lengths) are measured; bold-keyword and
   labelled-skills conventions are detected. A dry-run render validates the map before the template is
   accepted; a thumbnail is rendered when a PDF converter exists.

Rendering (`templates/generic.py`) clones the original paragraphs as prototypes, so fonts, colours,
spacing, numbering, indents and tab stops are the template's own; header lines are rebuilt from their
pattern, each token borrowing the run formatting of the text it replaces (uppercase conventions kept,
runs of alignment tabs replaced by one right tab stop). The three built-ins go through the same path.

Requirements for an upload: `.docx` (not PDF), single column, a name, a summary, a skills list, and at
least one job with bullets. Tables are kept verbatim but not filled.

## Recommendation

After the analysis, every template in the library is ranked for the job (`recommend.py`): seniority signal,
industry culture, room for concrete achievements vs narrative, ATS-friendliness (bold keywords, labelled
skills), page norms, and how many positions the layout was designed for. The best is pre-selected; each card
shows its score and a one-sentence reason. You can pick any.

## How the writing works

**Analysis** (`research.py`): Tavily extracts the JD; the fast model pulls facts; ~12 targeted searches
(products, engineering blog, news, mission/slogans, competitors, partners, hiring team, LinkedIn, roadmap) are
digested into a hiring brief: industry, products, **projects they are working on right now in plain words**,
focus, hiring goal, responsibilities, preferred experience/knowledge, tech stack, wanted achievements,
competitors with differences, partners, culture signals, 30-45 ranked ATS keywords, 10-15 realistic
"story hooks", and a plain-language summary for the UI.

**Writing** (`writer.py`): each past employer is researched so bullets use that company's real domain and
plausible components; the best model drafts against the template's measured budgets and the human-writing
rules (`humanize.py`: no you/they, banned AI vocabulary, overused-word cap, no stock constructions, varied
openers, numbers in roughly half the bullets, comma-list tech scopes). Deterministic checks list every
violation plus the top JD keywords still missing; up to three fix passes correct only those fields.

**ATS self-score** (`ats.py`, 100 pts, every point explained): keyword coverage 40 (phrases like
"PostgreSQL (schema design and query tuning)" match on their head term / tokens) · title alignment 10 ·
section integrity 10 · parse friendliness 10 · measurable results 10 · human writing 10 · template fit 10.

**Feedback loop**: free-text feedback → the writer edits the current JSON keeping untouched bullets
identical → same checks → new version (history kept; earlier versions downloadable).

## Project layout

```
backend/app/
  main.py         FastAPI: settings, templates (list/upload/delete/preview), sessions, jobs, generate,
                  revise, complete, downloads, html preview, static UI (desktop mode)
  research.py     JD analysis + employer research      recommend.py  template ranking
  writer.py       drafting, fix loop, revision          humanize.py   anti-AI-text rules
  ats.py          ATS self-score                        render.py     Word / LibreOffice / none, PyMuPDF
  config.py       settings.json > env > bundled keys    jobs.py storage.py llm.py search.py models.py
  templates/      analyzer.py (docx -> map), generic.py (map -> docx), engine.py (run-level fill),
                  registry.py (library), builtin/{nam,doi,daniel}/{template.docx,map.json,preview.png}
backend/desktop.py, resume_builder.spec       desktop entry + PyInstaller spec
backend/tests/test_e2e_mock.py                offline smoke test (no keys): python tests/test_e2e_mock.py
frontend/src/    React wizard: Setup (JD + library) -> Analysis (brief + ranked templates) -> Profile -> Result
tools/bake_keys.py, build_exe.bat, .github/workflows/build-exe.yml
deploy/          deploy.ps1 (from Windows) + server-setup.sh (on the server)
docs/template-analysis.md                     measurements of the three built-in templates
```

## 6. Deploy to a Linux server (Docker)

```powershell
powershell -ExecutionPolicy Bypass -File deploy\deploy.ps1 -Server hades-server -EnvFile .\.env -Port 3333
```
On locked-down hosts (multiple Docker networks, Tailscale, nftables) publish through host networking:
see the `docker-compose.override.yml` example in deploy/ notes — frontend `listen 3333`, backend on `5151`.

# Template analysis

Five files were supplied; two are PDF exports of the DOCX files (same producer "Microsoft Word 2016",
same fonts, same text), so there are **three distinct templates**. The DOCX is the source of truth for
each; the PDF confirms the intended rendering (e.g. the "Skills & Abilities" / "Experience" headings that
are empty `Heading 1` paragraphs in `Nam Nguyen 1.docx` but visible in `Nam Nguyen 3.pdf` - the engine fills
them in).

All measurements come from the OOXML (`w:sz` is half-points, `w:spacing` is twips = 1/20 pt, EMU = 1/914400 in).

## Template `nam` - "Classic Teal" (Nam Nguyen 1.docx / Nam Nguyen 3.pdf)

| Item | Value |
|---|---|
| Page | US Letter 8.5 × 11 in; margins top 0.7 / bottom 0.8 / left 0.8 / right 0.8 in |
| Theme fonts | major = Cambria, minor = Cambria (everything is Cambria) |
| Default run | 11 pt, paragraph `spacing after = 240 twips (12 pt)` |
| Title (name + headline) | style *Title*, 22 pt (run `w:sz=44`), colour #2A7B88, justified; text "Nam Nguyen (Senior Full Stack Engineer)" |
| Contact line | style *Heading 3*, 10 pt, colour #404040, `before 270 / after 45 twips`; "Vietnam \| email" |
| Section heading (About me / Skills & Abilities / Experience / Education) | *Heading 1*: 14 pt bold, #2A7B88, `before 320 / after 100 twips` |
| Summary | *Heading 1* paragraph overridden to 11 pt, not bold, colour #3A3836, justified, leading two spaces; **784 chars**, with `Strong` runs on 5 key phrases |
| Skill lines | *List Bullet*, 10.5 pt (first) / 11 pt, `line 288 auto` (1.2), justified, "A / B / C" items; 8 lines, 28-136 chars |
| Company line | *Heading 3* + bold + `w:caps`, colour #262626, 12 pt; company bold, "(Country)" italic, dates italic 9 pt right-aligned via a run of tabs (engine replaces with one right tab stop at 9900 twips) |
| Role line | *Heading 2* overridden to 11 pt, #404040, leading two spaces |
| Technical Scope | *Normal*, hanging indent `left 1890 / hanging 1620 twips`, 175-257 chars |
| Achievement bullets | *List Bullet*, 11 pt, justified; 10 / 7 / 6 per company (23 total), 149-279 chars, avg ≈ 200 |
| Spacers | empty *List Bullet* paragraphs (2) between companies; URL line is a *List Bullet* with `numId 0` (no bullet glyph) |
| Education | *Heading 2* × 2: "Bachelor of computer Science \| 2017 \|" then the university |

## Template `doi` - "Executive Blue" (Yusuke Doi 1.docx / .pdf)

| Item | Value |
|---|---|
| Page | US Letter; margins 0.7 / 0.8 / 0.8 / 0.8 in |
| Theme fonts | Cambria body; headings forced to **Gill Sans MT** (Segoe UI appears in the PDF as fallback) |
| Default run | 10.5 pt, `after 120`, `line 264 auto` (1.1) |
| Title | *Title*, Gill Sans MT 40 pt, #365F91, letter-spacing −7 |
| Contact line | *Normal* 11 pt: "Japan – Open to Remote Worldwide \| " + HYPERLINK field email (Hyperlink char style) |
| Section headings | *Heading 1* Gill Sans MT 18 pt, #365F91, ALL CAPS text, `before 400 / after 40`, bottom rule from the style |
| Summary | *Normal*, 12 pt, colour #0F243E, justified, `before/after 100 autospacing`, single line spacing; **535 chars** |
| Skill lines | *Normal* 12 pt, `before 240 / after 240`, `ind left 270 right 306`; **bold label** + ": items"; 6 lines: Languages, Frameworks, Databases, Cloud / Infrastructure, Testing / Observability, Tools / Practices (36-174 chars) |
| Role line | *Normal (Web)* 13 pt, #0F243E, `before 120 / after 40`: **"Role \| [Company]"** (Strong) + line break + "[Location, Remote] \| [2024 – Present]" |
| Company blurb | *Normal* 12 pt italic, `ind left 360`, `before 240`; 260-360 chars, first person allowed |
| Achievement paragraphs | *Normal* 12 pt, `numPr numId 23` (list item), `before 240 / after 0`, single spacing; 6 / 5 / 4 / 5 (20 total), 131-315 chars, avg ≈ 275; prose, no bold |
| Spacer | one empty *Normal* between companies, two before EDUCATION |
| Education | university bold 12 pt (`spacing −2`, `line 20 atLeast`), then "Bachelor's Degree in Computer Science" |
| Footer | "Page N" field |

## Template `daniel` - "Compact Modern" (Senior Full Stack Engineer - Daniel.docx)

| Item | Value |
|---|---|
| Page | **A4** 8.27 × 11.69 in; margins top 0.10 / bottom 0.19 / left 0.17 / right 0.15 in (very tight) |
| Fonts | *Normal* = Calibri 11 pt; *Heading 1* = Arial Black 16 pt; header box uses Arial Black 28 pt + Segoe UI 10.5 pt + Calibri Light 12 pt |
| Header | first body paragraph holds an inline **drawing group**: grey PNG band (7127240 × 1758950 EMU ≈ 7.8 × 1.9 in) + a text box with 3 centred paragraphs: name (Arial Black 28 pt), location (Segoe UI 10.5 pt, spacing 12), "# email" (Calibri Light 12 pt, yellow #FFC000 marker, email #0462C1 underlined). A VML `mc:Fallback` copy exists; the engine rewrites both |
| "Summary" heading | *Heading 1* (Arial Black 16 pt), `before 257 twips` |
| Summary | *Heading 1* paragraph overridden to Calibri 12 pt, leading space; **576 chars** |
| Skill lines | *Normal* 12 pt, `line 535 auto` (≈ 2.23), `ind left 427 right 380`; items separated by " / "; 7 visual lines (some joined by `w:br`), 60-105 chars |
| "Experience" heading | *Normal* run Arial Black 16 pt, `before 233680 EMU` |
| Role line | *Normal* 12 pt, `before 122`, `ind left 427`: **bold role** " –" + normal " 03/2024 to Present" |
| Company line | bold 12 pt "Company (Country) " + bold-italic **Remote** in #548DD4 |
| Technical Scope | `ind left 2430 hanging 1710`, `before 57`: bold-italic label + italic 10.5 pt list, 235-385 chars |
| "Key Achievements:" | *Heading 3* (bold 11 pt), `before 59` |
| Bullets | *List Paragraph* + `numId 1`, tab stop 1147, `line 267 exact` (13.35 pt), 10.5 pt, **bold keyword runs** (2-4 per bullet); 10 / 10 / 10 / 9 (39 total), 126-254 chars, avg ≈ 190 |
| URL line | *List Paragraph* without numbering, bold #548DD4 10.5 pt |
| Education | *Heading 1* "Education"; "Bachelor of Science: **Computer Science** 2013 - 2017" (12 pt) ; "THE UNIVERSITY OF SYDNEY" bold 12 pt |

## How the engine preserves all of this

`backend/app/templates/engine.py` never creates formatting. It deep-copies one prototype `<w:p>` per role from
the original file (so `pPr`, numbering, indents, tab stops, shading, exact line spacing all come along),
strips its runs, and re-emits runs whose `<w:rPr>` is cloned from the prototype run with the closest
bold/italic/underline/hyperlink flags. The body is cleared down to the final `<w:sectPr>` (page size and
margins) and rebuilt in template order by `registry.py::compose_<template>`.

Length budgets (`registry.py::Budget`) are the measured values above ±8 %; the writer is told them, the fix
loop enforces them, and the ATS "Template fit" check reports any drift.

## Generic analysis (v2)

Since v2 the three built-ins are not hand-mapped any more: they are analysed by the same pipeline as uploads
(`analyzer.py`) and shipped as `builtin/<id>/map.json` (curated names and heading texts only). The tables above
remain accurate; the maps additionally store per-paragraph roles, header patterns with original values, the
learned job block, and measured budgets. Upload any other single-column .docx resume to add a template.

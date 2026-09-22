export type TemplateInfo = {
  id: string; name: string; description: string; style_summary: string; tone: string; best_for: string[]
  page: string; fonts: string; builtin: boolean; source_name: string; has_preview: boolean; preview_url: string
  budget: { summary_chars: number; skill_lines: number; total_bullets: number; bullet_chars: [number, number]; bold_keywords: boolean; labelled_skills: boolean }
  features: Record<string, any>
}

export type Job = { id: string; kind: string; status: 'running' | 'done' | 'error'; messages: string[]; result: any; error: string | null; elapsed: number }

export type Contact = { email: string; phone: string; linkedin: string; github: string; website: string }
export type CompanyInput = { name: string; location: string; remote: boolean; role_title: string; start: string; end: string; website: string; notes: string }
export type EducationInput = { university: string; degree: string; field: string; start_year: string; end_year: string }
export type ProfileInput = { full_name: string; headline: string; location: string; contact: Contact; companies: CompanyInput[]; education: EducationInput; extra_context: string }

export type Intel = {
  company_name: string; role_title: string; industry: string; sub_industry: string; company_summary: string
  projects_plain: string[]
  plain_summary: Record<string, any>; ats_keywords: string[]; must_have_skills: string[]; sources: string[]
  competitors: { name: string; what_they_do: string; difference: string }[]; hiring_goal: string
}

export type TemplateScore = { template_id: string; score: number; reason: string }
export type ATSCheck = { name: string; score: number; max_score: number; detail: string; items: string[] }
export type ATSReport = { total: number; grade: string; checks: ATSCheck[]; matched_keywords: string[]; missing_keywords: string[]; flagged_phrases: string[]; length_report: any }

export type Session = {
  id: string; template_id: string; jd_url: string; intel: Intel | null; profile: ProfileInput | null
  recommendation: TemplateScore[]
  content: any; ats: ATSReport | null; version: number; history: any[]; status: string
}

export type Health = { ok: boolean; missing_keys: string[]; model: string; fast_model: string; render: { word: boolean; libreoffice: boolean }; key_sources: Record<string, string>; desktop: boolean; data_dir: string }
export type Settings = { ANTHROPIC_API_KEY: string; TAVILY_API_KEY: string; CLAUDE_MODEL: string; CLAUDE_FAST_MODEL: string; sources: Record<string, string> }

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = r.statusText
    try {
      const d = (await r.json()).detail
      if (d) msg = typeof d === 'string' ? d : JSON.stringify(d)
    } catch { /* ignore */ }
    throw new Error(msg)
  }
  return r.json()
}
const json = (body: unknown) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const api = {
  health: () => fetch('/api/health').then(j<Health>),
  settings: () => fetch('/api/settings').then(j<Settings>),
  saveSettings: (s: Partial<Record<keyof Settings, string>>) => fetch('/api/settings', json(s)).then(j<Settings>),
  templates: () => fetch('/api/templates').then(j<TemplateInfo[]>),
  uploadTemplate: (file: File) => {
    const fd = new FormData(); fd.append('file', file)
    return fetch('/api/templates', { method: 'POST', body: fd }).then(j<{ job_id: string }>)
  },
  deleteTemplate: (id: string) => fetch(`/api/templates/${id}`, { method: 'DELETE' }).then(j<{ ok: boolean }>),
  createSession: (jd_url: string) => fetch('/api/sessions', json({ jd_url })).then(j<{ session_id: string; job_id: string }>),
  session: (sid: string) => fetch(`/api/sessions/${sid}`).then(j<Session>),
  selectTemplate: (sid: string, template_id: string) => fetch(`/api/sessions/${sid}/template`, json({ template_id })).then(j<{ ok: boolean }>),
  job: (id: string) => fetch(`/api/jobs/${id}`).then(j<Job>),
  generate: (sid: string, profile: ProfileInput) => fetch(`/api/sessions/${sid}/generate`, json({ profile })).then(j<{ job_id: string }>),
  revise: (sid: string, feedback: string) => fetch(`/api/sessions/${sid}/revise`, json({ feedback })).then(j<{ job_id: string }>),
  complete: (sid: string) => fetch(`/api/sessions/${sid}/complete`, { method: 'POST' }).then(j<{ docx: string; pdf: string }>),
}

/** Poll a job until it finishes; onMessage receives the progress log each tick. */
export async function waitForJob(jobId: string, onMessage: (msgs: string[]) => void): Promise<Job> {
  for (;;) {
    const job = await api.job(jobId)
    onMessage(job.messages)
    if (job.status !== 'running') return job
    await new Promise(r => setTimeout(r, 1500))
  }
}

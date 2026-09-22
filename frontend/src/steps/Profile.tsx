import { useState } from 'react'
import { api, CompanyInput, ProfileInput, Session, waitForJob } from '../api'
import Progress from './Progress'

const emptyCompany = (): CompanyInput => ({ name: '', location: '', remote: false, role_title: '', start: '', end: 'Present', website: '', notes: '' })
const STORAGE_KEY = 'resume-builder-profile'

function loadDraft(): ProfileInput | null {
  try { const s = localStorage.getItem(STORAGE_KEY); return s ? JSON.parse(s) : null } catch { return null }
}

export default function Profile({ session, onBack, onDone }: { session: Session; onBack: () => void; onDone: () => Promise<void> }) {
  const [p, setP] = useState<ProfileInput>(() => session.profile || loadDraft() || {
    full_name: '', headline: session.intel?.role_title || '', location: '',
    contact: { email: '', phone: '', linkedin: '', github: '', website: '' },
    companies: [emptyCompany(), emptyCompany()],
    education: { university: '', degree: 'Bachelor of Science', field: 'Computer Science', start_year: '', end_year: '' },
    extra_context: '',
  })
  const [busy, setBusy] = useState(false)
  const [msgs, setMsgs] = useState<string[]>([])
  const [error, setError] = useState('')

  const up = (patch: Partial<ProfileInput>) => setP(prev => ({ ...prev, ...patch }))
  const upCompany = (i: number, patch: Partial<CompanyInput>) =>
    setP(prev => ({ ...prev, companies: prev.companies.map((c, k) => k === i ? { ...c, ...patch } : c) }))
  const move = (i: number, d: number) => setP(prev => {
    const arr = [...prev.companies]; const j = i + d
    if (j < 0 || j >= arr.length) return prev
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
    return { ...prev, companies: arr }
  })

  const valid = p.full_name && p.location && (p.contact.email || p.contact.phone) && p.education.university
    && p.companies.length > 0 && p.companies.every(c => c.name && c.start && c.end)

  const submit = async () => {
    setError(''); setBusy(true); setMsgs(['Starting…'])
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(p)) } catch { /* ignore */ }
    try {
      const { job_id } = await api.generate(session.id, p)
      const job = await waitForJob(job_id, setMsgs)
      if (job.status === 'error') throw new Error(job.error || 'Generation failed')
      await onDone()
    } catch (e: any) { setError(e.message || String(e)); setBusy(false) }
  }

  if (busy) return <Progress title="Researching your employers and writing the resume (usually 2–5 minutes)" messages={msgs} />

  return (
    <div className="card">
      <h2>3. Your profile</h2>
      <p className="muted">Facts only — names, dates, contacts. The stories for each company are written from the job analysis plus research on each employer. Use the notes field to steer them.</p>

      <div className="row">
        <label className="field"><span>Full name *</span><input value={p.full_name} onChange={e => up({ full_name: e.target.value })} /></label>
        <label className="field"><span>Headline / title</span><input value={p.headline} placeholder={session.intel?.role_title} onChange={e => up({ headline: e.target.value })} /></label>
        <label className="field"><span>Location *</span><input value={p.location} placeholder="Hanoi, Vietnam · Open to remote" onChange={e => up({ location: e.target.value })} /></label>
      </div>
      <div className="row">
        <label className="field"><span>Email *</span><input value={p.contact.email} onChange={e => up({ contact: { ...p.contact, email: e.target.value } })} /></label>
        <label className="field"><span>Phone</span><input value={p.contact.phone} onChange={e => up({ contact: { ...p.contact, phone: e.target.value } })} /></label>
        <label className="field"><span>LinkedIn</span><input value={p.contact.linkedin} placeholder="linkedin.com/in/…" onChange={e => up({ contact: { ...p.contact, linkedin: e.target.value } })} /></label>
        <label className="field"><span>GitHub / website</span><input value={p.contact.github} onChange={e => up({ contact: { ...p.contact, github: e.target.value } })} /></label>
      </div>

      <h3>Work history <small className="muted">(most recent first)</small></h3>
      {p.companies.map((c, i) => (
        <div className="company" key={i}>
          <div className="company-head">
            <strong>Company {i + 1}</strong>
            <span className="spacer" />
            <button type="button" onClick={() => move(i, -1)} disabled={i === 0}>↑</button>
            <button type="button" onClick={() => move(i, 1)} disabled={i === p.companies.length - 1}>↓</button>
            <button type="button" className="danger" onClick={() => up({ companies: p.companies.filter((_, k) => k !== i) })} disabled={p.companies.length === 1}>Remove</button>
          </div>
          <div className="row">
            <label className="field"><span>Company name *</span><input value={c.name} onChange={e => upCompany(i, { name: e.target.value })} /></label>
            <label className="field"><span>Country / city</span><input value={c.location} placeholder="Australia" onChange={e => upCompany(i, { location: e.target.value })} /></label>
            <label className="field"><span>Role title <small>(blank = generated)</small></span><input value={c.role_title} onChange={e => upCompany(i, { role_title: e.target.value })} /></label>
          </div>
          <div className="row">
            <label className="field"><span>From *</span><input value={c.start} placeholder="Jan 2024" onChange={e => upCompany(i, { start: e.target.value })} /></label>
            <label className="field"><span>To *</span><input value={c.end} placeholder="Present" onChange={e => upCompany(i, { end: e.target.value })} /></label>
            <label className="field"><span>Website</span><input value={c.website} placeholder="https://" onChange={e => upCompany(i, { website: e.target.value })} /></label>
            <label className="field check"><input type="checkbox" checked={c.remote} onChange={e => upCompany(i, { remote: e.target.checked })} /><span>Remote</span></label>
          </div>
          <label className="field"><span>Notes / things to highlight <small>(optional)</small></span>
            <textarea rows={2} value={c.notes} placeholder="e.g. led the payments migration to Stripe; team of 6; mention the outage we fixed in 2023" onChange={e => upCompany(i, { notes: e.target.value })} />
          </label>
        </div>
      ))}
      <button type="button" onClick={() => up({ companies: [...p.companies, emptyCompany()] })}>+ Add company</button>

      <h3>Education</h3>
      <div className="row">
        <label className="field"><span>University *</span><input value={p.education.university} onChange={e => up({ education: { ...p.education, university: e.target.value } })} /></label>
        <label className="field"><span>Degree</span><input value={p.education.degree} onChange={e => up({ education: { ...p.education, degree: e.target.value } })} /></label>
        <label className="field"><span>Field</span><input value={p.education.field} onChange={e => up({ education: { ...p.education, field: e.target.value } })} /></label>
        <label className="field"><span>From</span><input value={p.education.start_year} placeholder="2013" onChange={e => up({ education: { ...p.education, start_year: e.target.value } })} /></label>
        <label className="field"><span>To</span><input value={p.education.end_year} placeholder="2017" onChange={e => up({ education: { ...p.education, end_year: e.target.value } })} /></label>
      </div>

      <label className="field"><span>Anything else the writer should know <small>(optional)</small></span>
        <textarea rows={3} value={p.extra_context} placeholder="Tone preferences, things to avoid, certifications, visa status…" onChange={e => up({ extra_context: e.target.value })} />
      </label>

      {error && <div className="error">{error}</div>}
      <div className="actions">
        <button onClick={onBack}>← Back to analysis</button>
        <button className="primary" disabled={!valid} onClick={submit}>Build my resume →</button>
      </div>
    </div>
  )
}

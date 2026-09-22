import { useEffect, useRef, useState } from 'react'
import { api, TemplateInfo, waitForJob } from '../api'
import Progress from './Progress'
import TemplateCard from './TemplateCard'

export default function Setup({ onDone }: { onDone: (sid: string) => Promise<void> }) {
  const [templates, setTemplates] = useState<TemplateInfo[]>([])
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [msgs, setMsgs] = useState<string[]>([])
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [upMsgs, setUpMsgs] = useState<string[]>([])
  const [upError, setUpError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const reload = () => api.templates().then(setTemplates).catch(e => setError(String(e.message)))
  useEffect(() => { reload() }, [])

  const start = async () => {
    setError(''); setBusy(true); setMsgs(['Starting…'])
    try {
      const { session_id, job_id } = await api.createSession(url)
      const job = await waitForJob(job_id, setMsgs)
      if (job.status === 'error') throw new Error(job.error || 'Analysis failed')
      await onDone(session_id)
    } catch (e: any) {
      setError(e.message || String(e)); setBusy(false)
    }
  }

  const upload = async (file: File) => {
    setUpError(''); setUploading(true); setUpMsgs(['Uploading…'])
    try {
      const { job_id } = await api.uploadTemplate(file)
      const job = await waitForJob(job_id, setUpMsgs)
      if (job.status === 'error') throw new Error(job.error || 'Template analysis failed')
      await reload()
    } catch (e: any) { setUpError(e.message || String(e)) }
    setUploading(false)
    if (fileRef.current) fileRef.current.value = ''
  }

  const remove = async (t: TemplateInfo) => {
    if (!confirm(`Remove template “${t.name}” from the library?`)) return
    try { await api.deleteTemplate(t.id); await reload() } catch (e: any) { setUpError(e.message) }
  }

  if (busy) return <Progress title="Analysing the job, researching the company and ranking your templates (usually 1–3 minutes)" messages={msgs} />

  return (
    <>
      <div className="card">
        <h2>1. Job description</h2>
        <p className="muted">Paste the public link to the job post. The template is chosen in the next step, after the analysis, so the app can recommend the best fit.</p>
        <label className="field">
          <span>Job description link <small>(public URL, no login required)</small></span>
          <input type="url" placeholder="https://company.com/careers/senior-full-stack-engineer" value={url} onChange={e => setUrl(e.target.value)} />
        </label>
        {error && <div className="error">{error}</div>}
        <div className="actions">
          <span />
          <button className="primary" disabled={!/^https?:\/\//.test(url)} onClick={start}>Analyse job &amp; company →</button>
        </div>
      </div>

      <div className="card">
        <div className="row between">
          <div>
            <h2>Template library <small className="muted">({templates.length})</small></h2>
            <p className="muted">Upload any resume as a Word file (.docx). The layout, fonts, spacing and section structure are analysed once and the template stays available for every future job.</p>
          </div>
          <div>
            <input ref={fileRef} type="file" accept=".docx" style={{ display: 'none' }} onChange={e => e.target.files?.[0] && upload(e.target.files[0])} />
            <button className="primary" disabled={uploading} onClick={() => fileRef.current?.click()}>+ Upload .docx template</button>
          </div>
        </div>
        {uploading && <Progress title="Analysing the new template (about a minute)" messages={upMsgs} />}
        {upError && <div className="error">{upError}</div>}
        <div className="templates">
          {templates.map(t => <TemplateCard key={t.id} t={t} onDelete={() => remove(t)} />)}
        </div>
      </div>
    </>
  )
}

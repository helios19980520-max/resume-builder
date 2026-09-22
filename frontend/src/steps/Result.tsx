import { useMemo, useState } from 'react'
import { api, Health, Session, waitForJob } from '../api'
import Progress from './Progress'

type Props = { session: Session; health: Health | null; onRefresh: () => Promise<Session>; onEditProfile: () => void; onChangeTemplate: () => void }

export default function Result({ session, health, onRefresh, onEditProfile, onChangeTemplate }: Props) {
  const [feedback, setFeedback] = useState('')
  const [busy, setBusy] = useState(false)
  const [msgs, setMsgs] = useState<string[]>([])
  const [error, setError] = useState('')
  const [done, setDone] = useState(session.status === 'complete')
  const ats = session.ats!
  const last = [...session.history].reverse().find(h => h.version)
  const hasPdf = last ? last.pdf !== false : true
  const previewUrl = useMemo(() => hasPdf
    ? `/api/sessions/${session.id}/preview.pdf?v=${session.version}`
    : `/api/sessions/${session.id}/preview.html?v=${session.version}`, [session.id, session.version, hasPdf])

  const revise = async () => {
    setError(''); setBusy(true); setMsgs(['Starting…'])
    try {
      const { job_id } = await api.revise(session.id, feedback)
      const job = await waitForJob(job_id, setMsgs)
      if (job.status === 'error') throw new Error(job.error || 'Revision failed')
      setFeedback(''); await onRefresh()
    } catch (e: any) { setError(e.message || String(e)) }
    setBusy(false)
  }

  const complete = async () => {
    await api.complete(session.id); setDone(true)
    window.open(`/api/sessions/${session.id}/download/docx`, '_blank')
    if (hasPdf) setTimeout(() => window.open(`/api/sessions/${session.id}/download/pdf`, '_blank'), 400)
  }

  if (busy) return <Progress title="Updating the resume from your feedback" messages={msgs} />

  const pct = (c: { score: number; max_score: number }) => Math.round((c.score / c.max_score) * 100)

  return (
    <div className="result">
      <div className="preview card">
        <div className="preview-head">
          <h2>4. Resume preview <small className="muted">v{session.version} · template {session.template_id}</small></h2>
          <div>
            <a className="btn" href={`/api/sessions/${session.id}/download/docx`}>Download .docx</a>
            {hasPdf && <a className="btn" href={`/api/sessions/${session.id}/download/pdf`}>Download .pdf</a>}
          </div>
        </div>
        {!hasPdf && (
          <div className="warn-box">No PDF converter (Microsoft Word or LibreOffice) was found on this computer, so the preview below is approximate. The .docx download keeps the template's exact formatting.
            {health && !health.render.word && !health.render.libreoffice && ' Install LibreOffice (free) or Word to get PDF previews and downloads.'}</div>
        )}
        <iframe title="resume preview" src={previewUrl} />
      </div>

      <aside className="side">
        <div className="card score">
          <div className="score-ring" style={{ ['--pct' as any]: ats.total }}>
            <div><b>{Math.round(ats.total)}</b><span>{ats.grade}</span></div>
          </div>
          <div>
            <h3>Self ATS score</h3>
            <p className="muted">Deterministic checks — every point is explained below.</p>
          </div>
        </div>

        <div className="card">
          {ats.checks.map(c => (
            <div className="check" key={c.name}>
              <div className="check-head"><span>{c.name}</span><b>{c.score}/{c.max_score}</b></div>
              <div className="bar"><i style={{ width: pct(c) + '%' }} /></div>
              <div className="check-detail">{c.detail}</div>
              {c.items?.length > 0 && <div className="chips small">{c.items.map((x, i) => <span key={i} className="chip warn">{x}</span>)}</div>}
            </div>
          ))}
          <details className="details">
            <summary>Matched keywords ({ats.matched_keywords.length})</summary>
            <div className="chips small">{ats.matched_keywords.map(k => <span key={k} className="chip ok">{k}</span>)}</div>
          </details>
          {session.history.filter(h => h.version).length > 1 && (
            <details className="details"><summary>Version history</summary>
              <ul className="plain">{session.history.filter(h => h.version).map(h => <li key={h.version}>v{h.version}: ATS {h.ats}{h.pages ? ` · ${h.pages} page(s)` : ''} · <a href={`/api/sessions/${session.id}/download/docx?v=${h.version}`}>docx</a></li>)}</ul>
            </details>
          )}
        </div>

        <div className="card">
          <h3>Feedback</h3>
          <p className="muted">Tell the writer what to change — e.g. “bullet 3 at DeliverMe is too generic, mention the WebSocket reconnect bug”, “shorter summary”, “fewer numbers”.</p>
          <textarea rows={5} value={feedback} onChange={e => setFeedback(e.target.value)} />
          {error && <div className="error">{error}</div>}
          <div className="actions column">
            <button disabled={!feedback.trim()} onClick={revise}>Apply feedback &amp; regenerate</button>
            <button className="primary" onClick={complete}>{done ? 'Download again' : hasPdf ? 'Complete & download (.docx + .pdf)' : 'Complete & download (.docx)'}</button>
            <div className="row center">
              <button className="link" onClick={onEditProfile}>Edit profile facts</button>
              <button className="link" onClick={onChangeTemplate}>Change template</button>
            </div>
          </div>
        </div>
      </aside>
    </div>
  )
}

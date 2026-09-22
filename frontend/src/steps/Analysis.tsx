import { useEffect, useState } from 'react'
import { api, Session, TemplateInfo } from '../api'
import TemplateCard from './TemplateCard'

function List({ items }: { items?: any }) {
  if (!items) return null
  const arr = Array.isArray(items) ? items : [items]
  if (!arr.length) return <p className="muted">—</p>
  return <ul className="plain">{arr.map((x, i) => <li key={i}>{typeof x === 'string' ? x : JSON.stringify(x)}</li>)}</ul>
}

export default function Analysis({ session, onBack, onNext }: { session: Session; onBack: () => void; onNext: (templateId: string) => Promise<void> }) {
  const it = session.intel!
  const ps = it.plain_summary || {}
  const [templates, setTemplates] = useState<TemplateInfo[]>([])
  const [tid, setTid] = useState(session.template_id || session.recommendation?.[0]?.template_id || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { api.templates().then(setTemplates).catch(e => setError(e.message)) }, [])

  const scores = new Map(session.recommendation.map(r => [r.template_id, r]))
  const ordered = [...templates].sort((a, b) => (scores.get(b.id)?.score ?? -1) - (scores.get(a.id)?.score ?? -1))

  const block = (title: string, body: any, wide = false) => (
    <section className={'tile' + (wide ? ' wide' : '')}>
      <h4>{title}</h4>
      {typeof body === 'string' ? <p>{body}</p> : <List items={body} />}
    </section>
  )

  const next = async () => {
    setError(''); setSaving(true)
    try { await api.selectTemplate(session.id, tid); await onNext(tid) } catch (e: any) { setError(e.message); setSaving(false) }
  }

  return (
    <div className="card">
      <h2>2. What we learned about <em>{it.company_name}</em> — {it.role_title}</h2>
      <p className="muted">Plain-language summary. Everything below feeds the writing step; the full analysis (keywords, story hooks, sources) is kept in the session.</p>
      <div className="grid">
        {block('Industry', ps.industry || it.industry)}
        {block('What they build', ps.what_they_build || [])}
        {block('Projects they are working on right now', ps.projects_now?.length ? ps.projects_now : it.projects_plain || [], true)}
        {block('Current focus', ps.current_focus || [])}
        {block('Why they are hiring', ps.why_hiring || it.hiring_goal)}
        {block('Competitors', ps.competitors || it.competitors?.map(c => `${c.name} – ${c.what_they_do}`) || [])}
        {block('Partners / companions', ps.partners || [])}
        {block('Tech they prefer', ps.tech_they_prefer || [])}
        {block('Experience they want', ps.experience_they_want || [])}
        {block('Achievements they want to see', ps.achievements_they_want || [])}
        {block('Phrases they use', ps.phrases_they_use || [])}
      </div>
      <details className="details">
        <summary>ATS keywords we will target ({it.ats_keywords?.length || 0})</summary>
        <div className="chips">{it.ats_keywords?.map(k => <span key={k} className="chip">{k}</span>)}</div>
      </details>
      <details className="details">
        <summary>Sources ({it.sources?.length || 0})</summary>
        <ul className="plain">{it.sources?.map(s => <li key={s}><a href={s} target="_blank" rel="noreferrer">{s}</a></li>)}</ul>
      </details>

      <h3>Choose a template <small className="muted">— ranked for this job</small></h3>
      <p className="muted">The recommendation weighs seniority, industry culture, how much room the role needs for concrete achievements, and ATS friendliness. You can pick any of them.</p>
      <div className="templates">
        {ordered.map((t, i) => (
          <TemplateCard key={t.id} t={t} selected={tid === t.id} score={scores.get(t.id)} rank={scores.has(t.id) ? i + 1 : undefined} onSelect={() => setTid(t.id)} />
        ))}
      </div>

      {error && <div className="error">{error}</div>}
      <div className="actions">
        <button onClick={onBack}>← Change job</button>
        <button className="primary" disabled={!tid || saving} onClick={next}>Use this template, enter my profile →</button>
      </div>
    </div>
  )
}

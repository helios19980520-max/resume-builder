import { TemplateInfo, TemplateScore } from '../api'

type Props = {
  t: TemplateInfo
  selected?: boolean
  score?: TemplateScore
  rank?: number
  onSelect?: () => void
  onDelete?: () => void
}

export default function TemplateCard({ t, selected, score, rank, onSelect, onDelete }: Props) {
  return (
    <div className={'tpl ' + (selected ? 'selected' : '') + (onSelect ? ' clickable' : '')} onClick={onSelect} role={onSelect ? 'button' : undefined}>
      <div className="tpl-thumb">
        {t.has_preview ? <img src={t.preview_url} alt={t.name} loading="lazy" /> : <div className="tpl-noimg">{t.name}</div>}
        {rank === 1 && <span className="badge best">Recommended</span>}
        {rank && rank > 1 && <span className="badge">#{rank}</span>}
        {!t.builtin && <span className="badge mine">Uploaded</span>}
      </div>
      <div className="tpl-body">
        <div className="tpl-name">{t.name}{score && <span className="tpl-score">{score.score}/100</span>}</div>
        {score && <div className="tpl-reason">{score.reason}</div>}
        <div className="tpl-desc">{t.description}</div>
        <div className="tpl-meta">{t.page}<br />{t.fonts}</div>
        <div className="tpl-meta">Summary ≈{t.budget.summary_chars} chars · {t.budget.skill_lines} skill lines · {t.budget.total_bullets} bullets{t.budget.bold_keywords ? ' · bold keywords' : ''}{t.budget.labelled_skills ? ' · labelled skills' : ''}</div>
        {t.best_for?.length > 0 && <div className="chips small">{t.best_for.slice(0, 4).map(b => <span key={b} className="chip">{b}</span>)}</div>}
        {onDelete && !t.builtin && (
          <button type="button" className="danger small" onClick={e => { e.stopPropagation(); onDelete() }}>Remove template</button>
        )}
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { api, Health, Settings } from '../api'

export default function SettingsModal({ health, onClose, onSaved }: { health: Health | null; onClose: () => void; onSaved: () => void }) {
  const [s, setS] = useState<Settings | null>(null)
  const [anth, setAnth] = useState('')
  const [tav, setTav] = useState('')
  const [model, setModel] = useState('')
  const [fast, setFast] = useState('')
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  useEffect(() => { api.settings().then(x => { setS(x); setModel(x.CLAUDE_MODEL); setFast(x.CLAUDE_FAST_MODEL) }).catch(e => setError(e.message)) }, [])

  const save = async () => {
    setError(''); setMsg('')
    try {
      const x = await api.saveSettings({ ANTHROPIC_API_KEY: anth || undefined, TAVILY_API_KEY: tav || undefined, CLAUDE_MODEL: model, CLAUDE_FAST_MODEL: fast })
      setS(x); setAnth(''); setTav(''); setMsg('Saved.'); onSaved()
    } catch (e: any) { setError(e.message) }
  }

  const src = (k: string) => s?.sources?.[k] || health?.key_sources?.[k] || ''

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal card" onClick={e => e.stopPropagation()}>
        <div className="row between"><h2>Settings</h2><button className="link" onClick={onClose}>✕</button></div>
        <p className="muted">Keys are stored on this computer only. Leave a key field empty to keep the current one.</p>

        <label className="field"><span>Anthropic API key <small>current: {s?.ANTHROPIC_API_KEY || 'not set'} ({src('ANTHROPIC_API_KEY')})</small></span>
          <input value={anth} placeholder="sk-ant-…" onChange={e => setAnth(e.target.value)} /></label>
        <label className="field"><span>Tavily API key <small>current: {s?.TAVILY_API_KEY || 'not set'} ({src('TAVILY_API_KEY')})</small></span>
          <input value={tav} placeholder="tvly-…" onChange={e => setTav(e.target.value)} /></label>
        <div className="row">
          <label className="field"><span>Main model <small>(research synthesis, writing)</small></span><input value={model} onChange={e => setModel(e.target.value)} /></label>
          <label className="field"><span>Fast model <small>(extraction, employer profiles, fixes)</small></span><input value={fast} onChange={e => setFast(e.target.value)} /></label>
        </div>

        {health && (
          <div className="tile">
            <h4>This computer</h4>
            <ul className="plain">
              <li>PDF preview: {health.render.word ? 'Microsoft Word found (exact rendering)' : health.render.libreoffice ? 'LibreOffice found' : 'no converter found — .docx is produced, preview is approximate. Install Word or LibreOffice for PDFs.'}</li>
              <li>Data folder: <code>{health.data_dir}</code></li>
            </ul>
          </div>
        )}
        {error && <div className="error">{error}</div>}
        {msg && <div className="ok-msg">{msg}</div>}
        <div className="actions"><button onClick={onClose}>Close</button><button className="primary" onClick={save}>Save</button></div>
      </div>
    </div>
  )
}

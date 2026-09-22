import { useEffect, useState } from 'react'
import { api, Health, Session } from './api'
import Setup from './steps/Setup'
import Analysis from './steps/Analysis'
import Profile from './steps/Profile'
import Result from './steps/Result'
import SettingsModal from './steps/SettingsModal'

type Step = 1 | 2 | 3 | 4
const STEPS = ['Job & templates', 'Analysis & template pick', 'Your profile', 'Resume & ATS score']

export default function App() {
  const [step, setStep] = useState<Step>(1)
  const [session, setSession] = useState<Session | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [showSettings, setShowSettings] = useState(false)

  const loadHealth = () => api.health().then(h => { setHealth(h); if (h.missing_keys.length) setShowSettings(true) })
    .catch(() => setHealth({ ok: false, missing_keys: ['backend unreachable'], model: '', fast_model: '', render: { word: false, libreoffice: false }, key_sources: {}, desktop: false, data_dir: '' }))
  useEffect(() => { loadHealth() }, [])

  // resume a session from the URL hash (#sid) after a refresh
  useEffect(() => {
    const sid = location.hash.replace('#', '')
    if (sid) api.session(sid).then(s => {
      setSession(s)
      setStep(s.content ? 4 : s.intel ? (s.profile ? 3 : 2) : 1)
    }).catch(() => { location.hash = '' })
  }, [])

  const refresh = async (sid: string) => { const s = await api.session(sid); setSession(s); location.hash = sid; return s }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand" onClick={() => { setStep(1); location.hash = '' }} role="button">
          <span className="logo">R</span>
          <div>
            <div className="title">Resume Builder</div>
            <div className="subtitle">Job-tailored resumes that keep your template intact</div>
          </div>
        </div>
        <div className="row">
          {health && (
            <div className={'health ' + (health.missing_keys.length ? 'bad' : 'ok')}>
              {health.missing_keys.length ? `Missing: ${health.missing_keys.join(', ')}` : `Ready · ${health.model}`}
            </div>
          )}
          <button className="ghost" onClick={() => setShowSettings(true)}>⚙ Settings</button>
        </div>
      </header>

      <ol className="stepper">
        {STEPS.map((s, i) => (
          <li key={s} className={i + 1 === step ? 'active' : i + 1 < step ? 'done' : ''}>
            <span className="num">{i + 1}</span>{s}
          </li>
        ))}
      </ol>

      <main className="content">
        {step === 1 && <Setup onDone={async sid => { await refresh(sid); setStep(2) }} />}
        {step === 2 && session && <Analysis session={session} onBack={() => setStep(1)} onNext={async () => { await refresh(session.id); setStep(3) }} />}
        {step === 3 && session && <Profile session={session} onBack={() => setStep(2)} onDone={async () => { await refresh(session.id); setStep(4) }} />}
        {step === 4 && session && <Result session={session} health={health} onRefresh={() => refresh(session.id)} onEditProfile={() => setStep(3)} onChangeTemplate={() => setStep(2)} />}
      </main>

      {showSettings && <SettingsModal health={health} onClose={() => setShowSettings(false)} onSaved={loadHealth} />}
    </div>
  )
}

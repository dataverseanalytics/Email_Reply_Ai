import { useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../App'

const PROVIDERS = {
  gmail: { label: 'Gmail', imap_host: 'imap.gmail.com', imap_port: 993, smtp_host: 'smtp.gmail.com', smtp_port: 465 },
  outlook: { label: 'Outlook / Microsoft 365', imap_host: 'outlook.office365.com', imap_port: 993, smtp_host: 'smtp.office365.com', smtp_port: 587 },
  zoho: { label: 'Zoho Mail', imap_host: 'imap.zoho.in', imap_port: 993, smtp_host: 'smtp.zoho.in', smtp_port: 465 },
  strato: { label: 'Strato', imap_host: 'imap.strato.de', imap_port: 993, smtp_host: 'smtp.strato.de', smtp_port: 465 },
  yahoo: { label: 'Yahoo', imap_host: 'imap.mail.yahoo.com', imap_port: 993, smtp_host: 'smtp.mail.yahoo.com', smtp_port: 465 },
}

const BLANK = { imap_host: '', imap_port: 993, smtp_host: '', smtp_port: 465, username: '', password: '', from_address: '', auto_draft: true, fetch_limit: 25, sync_interval: 5 }

const SYNC_INTERVALS = [
  [0, 'Off (only when I click)'],
  [2, 'Every 2 minutes'],
  [5, 'Every 5 minutes'],
  [15, 'Every 15 minutes'],
  [30, 'Every 30 minutes'],
  [60, 'Every hour'],
]

export default function Settings() {
  return (
    <div className="page">
      <h1>Settings</h1>
      <MailboxForm />
      <ProfileForm />
    </div>
  )
}

function MailboxForm() {
  const [acc, setAcc] = useState(BLANK)
  const [connected, setConnected] = useState(false)
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get('/mail-account').then((a) => { if (a) { setAcc({ ...BLANK, ...a, password: '' }); setConnected(true) } })
  }, [])

  const set = (k, num) => (e) => setAcc({ ...acc, [k]: num ? Number(e.target.value) : e.target.value })

  const applyProvider = (key) => {
    const { imap_host, imap_port, smtp_host, smtp_port } = PROVIDERS[key]
    setAcc({ ...acc, imap_host, imap_port, smtp_host, smtp_port })
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setStatus(null)
    try {
      const body = { ...acc, username: acc.username || acc.from_address, password: acc.password || null }
      await api.put('/mail-account', body)
      setConnected(true)
      setAcc({ ...acc, password: '' })
      setStatus({ type: 'ok', text: 'Mailbox connected. Both reading and sending work.' })
    } catch (err) {
      setStatus({ type: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="panel" onSubmit={submit}>
      <h2>Mailbox {connected && <span className="tag ok">Connected</span>}</h2>
      <p className="muted">
        New mail is read over IMAP and replies go out over SMTP. For Gmail, Outlook and Yahoo, turn on
        two-step verification and create an <em>app password</em>, then paste it below. Your normal password won't work.
      </p>
      <div className="chips">
        {Object.entries(PROVIDERS).map(([k, p]) => (
          <button type="button" key={k} className="chip" onClick={() => applyProvider(k)}>{p.label}</button>
        ))}
      </div>
      <div className="row-2">
        <label>Email address
          <input type="email" value={acc.from_address} onChange={set('from_address')} required />
        </label>
        <label>Login username <small className="muted">(usually your email)</small>
          <input value={acc.username} onChange={set('username')} placeholder={acc.from_address} />
        </label>
      </div>
      <label>{connected ? 'App password (leave blank to keep the saved one)' : 'App password'}
        <input type="password" value={acc.password} onChange={set('password')} required={!connected} autoComplete="new-password" />
      </label>
      <div className="row-4">
        <label>IMAP server<input value={acc.imap_host} onChange={set('imap_host')} required /></label>
        <label>IMAP port<input type="number" value={acc.imap_port} onChange={set('imap_port', true)} required /></label>
        <label>SMTP server<input value={acc.smtp_host} onChange={set('smtp_host')} required /></label>
        <label>SMTP port<input type="number" value={acc.smtp_port} onChange={set('smtp_port', true)} required /></label>
      </div>
      <div className="row-2">
        <label>Check for new mail automatically
          <select value={acc.sync_interval} onChange={set('sync_interval', true)}>
            {SYNC_INTERVALS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
        </label>
        <label>Emails to check each time
          <input type="number" min={1} max={200} value={acc.fetch_limit} onChange={set('fetch_limit', true)} />
        </label>
      </div>
      <label className="check">
        <input type="checkbox" checked={acc.auto_draft} onChange={(e) => setAcc({ ...acc, auto_draft: e.target.checked })} />
        Draft replies automatically when new mail arrives
      </label>
      <p className="muted small">
        Automatic checks run on the server, so they keep going with this page closed, as long as the backend is running.
      </p>
      {status && <p className={status.type === 'ok' ? 'notice ok' : 'error'} role="status">{status.text}</p>}
      <div className="actions">
        <button className="primary" disabled={busy}>{busy ? 'Testing connection…' : connected ? 'Save mailbox' : 'Connect mailbox'}</button>
      </div>
    </form>
  )
}

function ProfileForm() {
  const { user, setUser } = useAuth()
  const [form, setForm] = useState({ name: user.name, signature: user.signature, tone: user.tone, about: user.about })
  const [status, setStatus] = useState(null)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    try {
      setUser(await api.put('/profile', form))
      setStatus({ type: 'ok', text: 'Saved.' })
    } catch (err) {
      setStatus({ type: 'error', text: err.message })
    }
  }

  return (
    <form className="panel" onSubmit={submit}>
      <h2>How replies sound</h2>
      <div className="row-2">
        <label>Name replies are sent from<input value={form.name} onChange={set('name')} required /></label>
        <label>Tone<input value={form.tone} onChange={set('tone')} placeholder="warm, concise, no jargon" /></label>
      </div>
      <label>About you or your business
        <textarea rows={3} value={form.about} onChange={set('about')}
          placeholder="I run a handmade candle shop in Pune. We ship across India and reply to every customer personally." />
      </label>
      <label>Signature<textarea rows={3} value={form.signature} onChange={set('signature')} /></label>
      {status && <p className={status.type === 'ok' ? 'notice ok' : 'error'} role="status">{status.text}</p>}
      <div className="actions"><button className="primary">Save</button></div>
    </form>
  )
}

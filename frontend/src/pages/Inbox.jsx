import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

const FILTERS = [
  { key: 'drafted', label: 'Ready to review' },
  { key: 'new', label: 'No draft' },
  { key: 'drafting', label: 'Drafting' },
  { key: 'sent', label: 'Sent' },
  { key: 'ignored', label: 'Skipped' },
  { key: '', label: 'All' },
]

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const today = new Date()
  return d.toDateString() === today.toDateString()
    ? d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    : d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export default function Inbox() {
  const [stats, setStats] = useState(null)
  const [filter, setFilter] = useState('drafted')
  const [emails, setEmails] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [notice, setNotice] = useState(null)

  const refresh = useCallback(async () => {
    const [s, list] = await Promise.all([
      api.get('/stats'),
      api.get(filter ? `/emails?status=${filter}` : '/emails'),
    ])
    setStats(s)
    setEmails(list)
  }, [filter])

  useEffect(() => { refresh().catch((e) => setNotice({ type: 'error', text: e.message })) }, [refresh])

  // Poll while background drafts are being written.
  const drafting = stats?.counts?.drafting ?? 0
  useEffect(() => {
    if (!drafting) return
    const t = setInterval(() => refresh().catch(() => {}), 3000)
    return () => clearInterval(t)
  }, [drafting, refresh])

  const sync = async () => {
    setSyncing(true)
    setNotice(null)
    try {
      const r = await api.post('/emails/sync')
      setNotice({
        type: 'ok',
        text: r.fetched
          ? `Fetched ${r.fetched} new email${r.fetched > 1 ? 's' : ''}${r.drafting ? `, drafting ${r.drafting} replies` : ''}.`
          : 'No new emails.',
      })
      await refresh()
    } catch (e) {
      setNotice({ type: 'error', text: e.message })
    } finally {
      setSyncing(false)
    }
  }

  const counts = stats?.counts ?? {}

  if (stats && !stats.has_account) {
    return (
      <div className="page">
        <div className="empty-hero">
          <h1>Connect your mailbox to start</h1>
          <p>Add your IMAP and SMTP details so Replydesk can read new mail and send the replies you approve.</p>
          <Link className="button primary" to="/settings">Connect mailbox</Link>
          {stats.knowledge === 0 && (
            <p className="muted">While you're there, add a few <Link to="/knowledge">saved answers</Link> so drafts have facts to work from.</p>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className={`inbox ${selectedId ? 'has-selection' : ''}`}>
      <section className="list-pane">
        <header className="list-head">
          <div className="tally">
            <strong>{counts.drafted ?? 0}</strong> to review
            {drafting > 0 && <span className="pulse"> · {drafting} drafting</span>}
          </div>
          <button className="primary" onClick={sync} disabled={syncing}>
            {syncing ? 'Checking…' : 'Check for new mail'}
          </button>
        </header>
        {notice && <p className={`notice ${notice.type}`} role="status">{notice.text}</p>}
        <div className="filters" role="tablist">
          {FILTERS.map((f) => (
            <button key={f.key} role="tab" aria-selected={filter === f.key}
              className={filter === f.key ? 'active' : ''} onClick={() => setFilter(f.key)}>
              {f.label}
              {f.key && counts[f.key] ? <span className="count">{counts[f.key]}</span> : null}
            </button>
          ))}
        </div>
        <ul className="mail-list">
          {emails.length === 0 && (
            <li className="list-empty">
              {filter === 'drafted' ? 'Nothing waiting for review. Check for new mail to pull in the latest messages.' : 'No emails here.'}
            </li>
          )}
          {emails.map((m) => (
            <li key={m.id}>
              <button className={`mail-row ${selectedId === m.id ? 'selected' : ''}`} onClick={() => setSelectedId(m.id)}>
                <span className="row-top">
                  <span className="sender">{m.from_name || m.from_address}</span>
                  <span className="date">{formatDate(m.received_at)}</span>
                </span>
                <span className="subject">{m.subject || '(no subject)'}</span>
                <span className="preview">{m.preview}</span>
                {m.status === 'drafting' && <span className="tag drafting">Drafting</span>}
                {m.draft_note && m.status === 'drafted' && <span className="tag check">Check before sending</span>}
                {m.draft_error && <span className="tag err">Draft failed</span>}
              </button>
            </li>
          ))}
        </ul>
      </section>
      <section className="detail-pane">
        {selectedId
          ? <EmailDetail key={selectedId} id={selectedId} onBack={() => setSelectedId(null)} onChange={refresh} />
          : <div className="detail-empty">Select an email to read it and review its reply.</div>}
      </section>
    </div>
  )
}

function EmailDetail({ id, onBack, onChange }) {
  const [email, setEmail] = useState(null)
  const [draft, setDraft] = useState('')
  const [presets, setPresets] = useState([])
  const [instruction, setInstruction] = useState('')
  const [busy, setBusy] = useState('') // 'draft' | 'send' | 'save'
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    const e = await api.get(`/emails/${id}`)
    setEmail(e)
    setDraft(e.draft_body)
    return e
  }, [id])

  useEffect(() => {
    load().catch((e) => setError(e.message))
    api.get('/presets').then(setPresets).catch(() => {})
  }, [load])

  // If this email is still being drafted in the background, wait for it.
  useEffect(() => {
    if (email?.status !== 'drafting') return
    const t = setInterval(() => load().catch(() => {}), 3000)
    return () => clearInterval(t)
  }, [email?.status, load])

  if (!email) return <div className="detail-empty">{error || 'Loading…'}</div>

  const dirty = draft !== email.draft_body
  const hasDraft = !!email.draft_body

  const generate = async (text, revise) => {
    setBusy('draft')
    setError('')
    try {
      const e = await api.post(`/emails/${id}/draft`, { instruction: text, revise })
      setEmail(e)
      setDraft(e.draft_body)
      if (e.draft_error) setError(e.draft_error)
      else setInstruction('')
      onChange()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  const act = async (kind, fn) => {
    setBusy(kind)
    setError('')
    try {
      const e = await fn()
      setEmail(e)
      setDraft(e.draft_body)
      onChange()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  const sent = email.status === 'sent'
  const drafting = email.status === 'drafting' || busy === 'draft'

  return (
    <article className="detail">
      <button className="link back" onClick={onBack}>Back to list</button>
      <header className="detail-head">
        <h2>{email.subject || '(no subject)'}</h2>
        <p className="from">
          <strong>{email.from_name || email.from_address}</strong>
          {email.from_name && <span className="muted"> &lt;{email.from_address}&gt;</span>}
          <span className="muted"> · {new Date(email.received_at).toLocaleString()}</span>
        </p>
      </header>
      <div className="original">{email.body || '(empty message)'}</div>

      <div className="composer">
        <div className="composer-head">
          <h3>{sent ? 'Your reply (sent)' : 'Your reply'}</h3>
          {email.draft_prompt && !sent && <span className="muted small">Last instruction: “{email.draft_prompt}”</span>}
        </div>
        {email.draft_note && !sent && <p className="ai-note"><strong>Check before sending:</strong> {email.draft_note}</p>}
        {error && <p className="error" role="alert">{error}</p>}

        {drafting && !hasDraft
          ? <div className="sheet placeholder">Writing a reply from your saved answers…</div>
          : (
            <textarea className="sheet" value={draft} onChange={(e) => setDraft(e.target.value)}
              readOnly={sent} placeholder="No draft yet. Write one, or ask the AI below." aria-label="Reply" />
          )}

        {!sent && (
          <>
            <form className="prompt-bar" onSubmit={(e) => { e.preventDefault(); if (instruction.trim()) generate(instruction, hasDraft) }}>
              <input value={instruction} onChange={(e) => setInstruction(e.target.value)} disabled={drafting}
                placeholder={hasDraft ? 'Tell the AI how to change this reply, e.g. "mention our weekend hours"' : 'Tell the AI what this reply should say'} />
              <button className="secondary" disabled={drafting || !instruction.trim()}>
                {drafting ? 'Writing…' : hasDraft ? 'Rewrite' : 'Write reply'}
              </button>
            </form>
            <div className="chips">
              {email.suggested_prompts.map((p) => (
                <button key={`s-${p}`} className="chip suggested" disabled={drafting} onClick={() => generate(p, true)} title="Suggested by AI for this email">
                  {p}
                </button>
              ))}
              {presets.map((p) => (
                <button key={`p-${p.id}`} className="chip" disabled={drafting} onClick={() => generate(p.text, hasDraft)} title={p.text}>
                  {p.label}
                </button>
              ))}
            </div>
            <div className="actions">
              <button className="primary" disabled={!draft.trim() || !!busy}
                onClick={() => act('send', () => api.post(`/emails/${id}/send`, { draft_body: draft }))}>
                {busy === 'send' ? 'Sending…' : 'Send reply'}
              </button>
              <button className="secondary" disabled={!dirty || !!busy}
                onClick={() => act('save', () => api.put(`/emails/${id}/draft`, { draft_body: draft }))}>
                {busy === 'save' ? 'Saving…' : 'Save draft'}
              </button>
              <button className="secondary" disabled={drafting} onClick={() => generate('', false)}>
                {hasDraft ? 'Write a fresh draft' : 'Draft with AI'}
              </button>
              {email.status === 'ignored'
                ? <button className="link" onClick={() => act('', () => api.patch(`/emails/${id}`, { status: 'new' }))}>Move back to inbox</button>
                : <button className="link" disabled={!!busy} onClick={() => act('', () => api.patch(`/emails/${id}`, { status: 'ignored' }))}>Skip this email</button>}
            </div>
          </>
        )}
      </div>
    </article>
  )
}

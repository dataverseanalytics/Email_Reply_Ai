import { useEffect, useState } from 'react'
import { api } from '../api'

const EMPTY = { question: '', answer: '' }

export default function Knowledge() {
  const [items, setItems] = useState([])
  const [form, setForm] = useState(EMPTY)
  const [editingId, setEditingId] = useState(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')

  useEffect(() => { api.get('/knowledge').then(setItems).catch((e) => setError(e.message)) }, [])

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    try {
      if (editingId) {
        const saved = await api.put(`/knowledge/${editingId}`, form)
        setItems(items.map((i) => (i.id === editingId ? saved : i)))
      } else {
        setItems([await api.post('/knowledge', form), ...items])
      }
      setForm(EMPTY)
      setEditingId(null)
    } catch (err) {
      setError(err.message)
    }
  }

  const remove = async (id) => {
    if (!confirm('Delete this answer?')) return
    await api.del(`/knowledge/${id}`)
    setItems(items.filter((i) => i.id !== id))
  }

  const q = query.toLowerCase()
  const shown = items.filter((i) => !q || i.question.toLowerCase().includes(q) || i.answer.toLowerCase().includes(q))

  return (
    <div className="page">
      <h1>Saved answers</h1>
      <p className="lede">
        Questions people often ask you, and how you answer them. Drafts use these as the facts and
        put them in new words for each sender, so no two replies are copies.
      </p>

      <form className="panel" onSubmit={submit}>
        <label>Question
          <input value={form.question} onChange={(e) => setForm({ ...form, question: e.target.value })}
            placeholder="What are your delivery charges?" required />
        </label>
        <label>Your answer
          <textarea rows={4} value={form.answer} onChange={(e) => setForm({ ...form, answer: e.target.value })}
            placeholder="Free delivery on orders above ₹999. Below that it's a flat ₹60, delivered in 3–5 working days." required />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="actions">
          <button className="primary">{editingId ? 'Save changes' : 'Add answer'}</button>
          {editingId && <button type="button" className="link" onClick={() => { setEditingId(null); setForm(EMPTY) }}>Cancel</button>}
        </div>
      </form>

      {items.length > 3 && (
        <input className="search" type="search" placeholder="Search answers" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search answers" />
      )}

      {items.length === 0
        ? <p className="muted">No answers yet. Start with the three questions you answer most often.</p>
        : (
          <ul className="qa-list">
            {shown.map((i) => (
              <li key={i.id} className="qa">
                <p className="q">{i.question}</p>
                <p className="a">{i.answer}</p>
                <div className="qa-actions">
                  <button className="link" onClick={() => { setEditingId(i.id); setForm({ question: i.question, answer: i.answer }); window.scrollTo({ top: 0, behavior: 'smooth' }) }}>Edit</button>
                  <button className="link danger" onClick={() => remove(i.id)}>Delete</button>
                </div>
              </li>
            ))}
          </ul>
        )}
    </div>
  )
}

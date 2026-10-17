import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Presets() {
  const [items, setItems] = useState([])
  const [form, setForm] = useState({ label: '', text: '' })
  const [error, setError] = useState('')

  useEffect(() => { api.get('/presets').then(setItems).catch((e) => setError(e.message)) }, [])

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    try {
      setItems([...items, await api.post('/presets', form)])
      setForm({ label: '', text: '' })
    } catch (err) {
      setError(err.message)
    }
  }

  const remove = async (id) => {
    await api.del(`/presets/${id}`)
    setItems(items.filter((i) => i.id !== id))
  }

  return (
    <div className="page">
      <h1>Reply prompts</h1>
      <p className="lede">
        One-click instructions that show under every draft. Click one to have the AI rewrite the
        reply that way. Each email also gets three prompts the AI suggests for that message.
      </p>

      <form className="panel" onSubmit={submit}>
        <div className="row-2">
          <label>Button name
            <input value={form.label} maxLength={40} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="Offer a discount" required />
          </label>
          <label>Instruction for the AI
            <input value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} placeholder="Offer 10% off their next order with code THANKS10." required />
          </label>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="actions"><button className="primary">Add prompt</button></div>
      </form>

      <ul className="preset-list">
        {items.map((p) => (
          <li key={p.id}>
            <span className="chip static">{p.label}</span>
            <span className="preset-text">{p.text}</span>
            <button className="link danger" onClick={() => remove(p.id)} aria-label={`Delete ${p.label}`}>Delete</button>
          </li>
        ))}
      </ul>
    </div>
  )
}

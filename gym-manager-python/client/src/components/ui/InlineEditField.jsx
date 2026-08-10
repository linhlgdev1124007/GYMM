import { useEffect, useState } from 'react'
import { Check, Pencil, X } from 'lucide-react'
import { Input, Select } from './Form'

export function InlineEditField({ label, value, displayValue, type = 'text', options = [], emptyAction = 'Thêm', onSave, pending, className = '' }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value ?? '')
  useEffect(() => setDraft(value ?? ''), [value])
  const close = () => { setDraft(value ?? ''); setEditing(false) }
  const save = async () => { await onSave(draft); setEditing(false) }
  return <div className={`inline-field ${className}`}><dt>{label}</dt><dd>
    {editing ? <div className="inline-field-editor">{type === 'select' ? <Select autoFocus value={draft} onChange={(e) => setDraft(e.target.value)}>{options.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</Select> : <Input autoFocus type={type} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') save(); if (e.key === 'Escape') close() }} />}<button onClick={save} disabled={pending} aria-label={`Lưu ${label}`}><Check size={15} /></button><button onClick={close} aria-label="Hủy"><X size={15} /></button></div> : <button className="inline-field-value" onClick={() => setEditing(true)}><span>{displayValue || value || <em>{emptyAction}</em>}</span><Pencil size={12} /></button>}
  </dd></div>
}

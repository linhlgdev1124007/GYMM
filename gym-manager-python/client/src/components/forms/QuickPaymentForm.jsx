import { useEffect, useState } from 'react'
import { Button } from '../ui/Button'
import { Field, Input, Select } from '../ui/Form'
import { Modal } from '../ui/Modal'
import { money } from '../../utils/format'

export function QuickPaymentForm({ membership, options, open, onClose, onSubmit, pending, error }) {
  const [form, setForm] = useState({ amount: 0, paymentMethod: 'cash', bankAccountId: '', receipt: null })
  useEffect(() => setForm({ amount: membership?.debtAmount || 0, paymentMethod: 'cash', bankAccountId: '', receipt: null }), [membership, open])
  if (!membership) return null
  const remaining = Math.max(Number(membership.debtAmount || 0) - Number(form.amount || 0), 0)
  const submit = (event) => {
    event.preventDefault()
    const payload = new FormData()
    payload.append('startsAt', membership.startsAt || '')
    payload.append('expiresAt', membership.expiresAt || '')
    payload.append('finalPrice', membership.finalPrice || 0)
    payload.append('paidAmount', Number(membership.paidAmount || 0) + Number(form.amount || 0))
    payload.append('debtDueDate', remaining ? membership.debtDueDate || '' : '')
    payload.append('paymentMethod', form.paymentMethod)
    payload.append('bankAccountId', form.bankAccountId)
    payload.append('status', membership.status === 'expiring' ? 'active' : membership.status)
    if (form.receipt) payload.append('receipt', form.receipt)
    onSubmit(payload)
  }
  return <Modal open={open} onClose={onClose} title="Thu tiền" description={`${membership.package.name} · Còn nợ ${money(membership.debtAmount)}`}><form onSubmit={submit}><div className="modal-body"><div className="form-grid"><Field className="form-span" label="Số tiền thu" required><Input autoFocus type="number" min="1" max={membership.debtAmount} value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></Field><Field label="Phương thức"><Select value={form.paymentMethod} onChange={(e) => setForm({ ...form, paymentMethod: e.target.value })}><option value="cash">Tiền mặt</option><option value="bank_transfer">Chuyển khoản</option><option value="card">Thẻ</option></Select></Field><Field label="Tài khoản nhận"><Select value={form.bankAccountId} onChange={(e) => setForm({ ...form, bankAccountId: e.target.value })}><option value="">Không áp dụng</option>{options?.bankAccounts?.map((row) => <option key={row.id} value={row.id}>{row.label}</option>)}</Select></Field><Field className="form-span" label="Ảnh phiếu thu"><Input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => setForm({ ...form, receipt: e.target.files[0] })} /></Field></div><div className="mt-4 flex justify-between border-t border-slate-100 pt-3 text-xs"><span className="text-slate-500">Công nợ sau giao dịch</span><strong className={remaining ? 'text-red-700' : 'text-emerald-700'}>{money(remaining)}</strong></div>{error && <div className="inline-error mt-4">{error}</div>}</div><div className="form-actions"><Button variant="secondary" onClick={onClose}>Hủy</Button><Button type="submit" disabled={pending || Number(form.amount) <= 0}>{pending ? 'Đang ghi nhận…' : 'Xác nhận thu tiền'}</Button></div></form></Modal>
}

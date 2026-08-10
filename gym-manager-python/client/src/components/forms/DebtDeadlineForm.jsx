import { useEffect, useState } from 'react'
import { format } from 'date-fns'
import { Button } from '../ui/Button'
import { Field, Input } from '../ui/Form'
import { Modal } from '../ui/Modal'
import { money } from '../../utils/format'

export function DebtDeadlineForm({ membership, open, onClose, onSubmit, pending, error }) {
  const [dueDate, setDueDate] = useState('')
  useEffect(() => setDueDate(membership?.debtDueDate || format(new Date(), 'yyyy-MM-dd')), [membership, open])
  if (!membership) return null
  return <Modal open={open} onClose={onClose} title={membership.debtDueDate ? 'Đổi hạn thanh toán' : 'Đặt hạn thanh toán'} description={`${membership.package.name} · Công nợ ${money(membership.debtAmount)}`}><form onSubmit={(event) => { event.preventDefault(); onSubmit({ debtDueDate: dueDate }) }}><div className="modal-body"><Field label="Hạn thanh toán" required><Input autoFocus type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)}/></Field>{error && <div className="inline-error mt-4">{error}</div>}</div><div className="form-actions"><Button variant="secondary" onClick={onClose}>Hủy</Button><Button type="submit" disabled={pending || !dueDate}>{pending ? 'Đang lưu…' : 'Lưu hạn thanh toán'}</Button></div></form></Modal>
}

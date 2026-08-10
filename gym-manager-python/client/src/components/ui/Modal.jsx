import { X } from 'lucide-react'
import { useEffect } from 'react'

export function Modal({ open, onClose, title, description, children, size = 'md' }) {
  useEffect(() => { if (!open) return; const close = (event) => event.key === 'Escape' && onClose(); document.addEventListener('keydown', close); return () => document.removeEventListener('keydown', close) }, [open, onClose])
  if (!open) return null
  return <div className="modal-layer" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section className={`modal modal-${size}`} role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <header className="modal-header"><div><h2 id="modal-title">{title}</h2>{description && <p>{description}</p>}</div><button className="icon-button" onClick={onClose} aria-label="Đóng"><X size={18} /></button></header>
      {children}
    </section>
  </div>
}

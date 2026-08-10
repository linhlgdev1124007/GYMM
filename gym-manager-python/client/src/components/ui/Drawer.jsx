import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'

export function Drawer({ open, onClose, title, description, children, footer, size = 'lg' }) {
  const panel = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const previous = document.activeElement
    const onKey = (event) => { if (event.key === 'Escape' && !document.querySelector('.modal-layer, .command-layer')) onClose() }
    document.addEventListener('keydown', onKey)
    requestAnimationFrame(() => panel.current?.focus())
    return () => { document.removeEventListener('keydown', onKey); previous?.focus?.() }
  }, [open, onClose])
  if (!open) return null
  return <div className="drawer-layer" role="presentation">
    <button className="drawer-backdrop" onClick={onClose} aria-label="Đóng bảng chi tiết" />
    <aside ref={panel} tabIndex={-1} className={`drawer ${size === 'xl' ? 'max-w-[680px]' : 'max-w-[560px]'} max-[640px]:max-w-none`} role="dialog" aria-modal="true" aria-labelledby="drawer-title">
      <header className="drawer-header"><div><h2 id="drawer-title">{title}</h2>{description && <p>{description}</p>}</div><button className="icon-button" onClick={onClose} aria-label="Đóng"><X size={18} /></button></header>
      <div className="drawer-body">{children}</div>
      {footer && <footer className="drawer-footer">{footer}</footer>}
    </aside>
  </div>
}

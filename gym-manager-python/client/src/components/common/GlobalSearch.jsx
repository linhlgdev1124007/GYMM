import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, UserRound, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api, queryString } from '../../services/api'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { StatusBadge } from '../ui/StatusBadge'

export function GlobalSearch() {
  const navigate = useNavigate(); const [open, setOpen] = useState(false); const [search, setSearch] = useState(''); const [active, setActive] = useState(0); const q = useDebouncedValue(search, 180)
  const results = useQuery({ queryKey: ['global-search', q], queryFn: () => api(`/api/members?${queryString({ q, page: 1, pageSize: 10 })}`), enabled: open && q.length >= 2 })
  const items = results.data?.items || []
  useEffect(() => { const shortcut = (event) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setOpen((value) => !value) } }; document.addEventListener('keydown', shortcut); return () => document.removeEventListener('keydown', shortcut) }, [])
  useEffect(() => { if (!open) { setSearch(''); setActive(0) } }, [open])
  const choose = (row) => { navigate(`/members?member=${row.id}`); setOpen(false) }
  return <><button className="global-search-trigger" onClick={() => setOpen(true)}><Search size={15}/><span>Tìm hội viên…</span><kbd>Ctrl K</kbd></button>{open && <div className="command-layer" onMouseDown={(event) => event.target === event.currentTarget && setOpen(false)}><section className="command-panel" role="dialog" aria-modal="true" aria-label="Tìm kiếm toàn hệ thống"><div className="command-input"><Search size={18}/><input autoFocus value={search} onChange={(event) => { setSearch(event.target.value); setActive(0) }} placeholder="Tên, số điện thoại hoặc mã hội viên…" onKeyDown={(event) => { if (event.key === 'Escape') setOpen(false); if (event.key === 'ArrowDown') { event.preventDefault(); setActive((value) => Math.min(value + 1, items.length - 1)) } if (event.key === 'ArrowUp') { event.preventDefault(); setActive((value) => Math.max(value - 1, 0)) } if (event.key === 'Enter' && items[active]) choose(items[active]) }}/><button onClick={() => setOpen(false)} aria-label="Đóng tìm kiếm"><X size={17}/></button></div><div className="command-results">{results.isLoading && <div className="space-y-2 p-3"><div className="skeleton h-12"/><div className="skeleton h-12"/><div className="skeleton h-12"/></div>}{items.map((row, index) => <button key={row.id} className={index === active ? 'active' : ''} onMouseEnter={() => setActive(index)} onClick={() => choose(row)}><div className="avatar avatar-md"><UserRound size={15}/></div><span><strong>{row.name}</strong><small>{row.code} · {row.phone || 'Chưa có SĐT'} · {row.membership?.package.name || 'Chưa có gói'}</small></span><StatusBadge status={row.membership?.status || row.status}/></button>)}{q.length < 2 && <p>Nhập ít nhất 2 ký tự để tìm kiếm. Dùng ↑ ↓ và Enter để thao tác nhanh.</p>}{q.length >= 2 && !results.isLoading && !items.length && <p>Không tìm thấy hội viên phù hợp.</p>}</div></section></div>}</>
}

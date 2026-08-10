import { Search, X } from 'lucide-react'
export function SearchInput({ value, onChange, placeholder = 'Tìm kiếm…' }) { return <div className="search-input"><Search size={16} /><input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />{value && <button onClick={() => onChange('')} aria-label="Xóa tìm kiếm"><X size={15} /></button>}</div> }

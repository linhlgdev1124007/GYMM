import { MoreHorizontal } from 'lucide-react'
export function RowMenu({ children }) { return <details className="row-menu" onClick={(event) => event.stopPropagation()}><summary aria-label="Mở menu thao tác"><MoreHorizontal size={18} /></summary><div>{children}</div></details> }

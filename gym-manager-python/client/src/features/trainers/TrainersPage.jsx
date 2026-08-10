import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { api, queryString } from '../../services/api'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { PageHeader } from '../../components/common/PageHeader'
import { SearchInput } from '../../components/common/SearchInput'
import { Button } from '../../components/ui/Button'
import { DataTable } from '../../components/ui/DataTable'
import { Field, Input } from '../../components/ui/Form'
import { Modal } from '../../components/ui/Modal'
import { Pagination } from '../../components/ui/Pagination'
import { RowMenu } from '../../components/ui/RowMenu'
import { initials } from '../../utils/format'

const blank={name:'',phone:'',email:'',title:'Coach'}
export function TrainersPage(){
  const client=useQueryClient();const[search,setSearch]=useState('');const q=useDebouncedValue(search);const[page,setPage]=useState(1);const[open,setOpen]=useState(false);const[selected,setSelected]=useState(null);const[confirm,setConfirm]=useState(null);const[form,setForm]=useState(blank);const[error,setError]=useState('')
  useEffect(()=>setForm(selected?{name:selected.name,phone:selected.phone||'',email:selected.email||'',title:selected.title||''}:blank),[selected,open])
  const query=useQuery({queryKey:['trainers',q,page],queryFn:()=>api(`/api/trainers?${queryString({q,page,pageSize:20})}`)})
  const edit=(row)=>{setSelected(row);setError('');setOpen(true)}
  const save=useMutation({mutationFn:(payload)=>api(selected?`/api/trainers/${selected.id}`:'/api/trainers',{method:selected?'PATCH':'POST',body:payload}),onSuccess:()=>{client.invalidateQueries({queryKey:['trainers']});client.invalidateQueries({queryKey:['member-options']});setOpen(false);setSelected(null);toast.success('Đã lưu nhân viên.')},onError:(e)=>setError(e.message)})
  const remove=useMutation({mutationFn:(row)=>api(`/api/trainers/${row.id}`,{method:'DELETE'}),onSuccess:(data)=>{client.invalidateQueries({queryKey:['trainers']});client.invalidateQueries({queryKey:['member-options']});setConfirm(null);toast.success(data.archived?'Nhân viên có lịch sử nên đã được ẩn an toàn.':'Đã xóa nhân viên.')}})
  const columns=[{key:'trainer',label:'Nhân viên',render:(r)=><button className="member-cell text-left" onClick={(e)=>{e.stopPropagation();edit(r)}}><div className="avatar avatar-md">{initials(r.name)}</div><div><span className="cell-primary hover:text-blue-700">{r.name}</span><div className="cell-secondary">{r.code}</div></div></button>},{key:'phone',label:'Điện thoại',render:(r)=>r.phone||'—'},{key:'title',label:'Chức danh',render:(r)=>r.title||'—'},{key:'activeClients',label:'Khách PT',className:'text-right',render:(r)=><Link to={`/members?trainerId=${r.id}`} className="font-medium text-blue-700 hover:underline" onClick={(e)=>e.stopPropagation()}>{r.activeClients}</Link>},{key:'ptSessions',label:'Buổi còn lại',className:'text-right'},{key:'actions',label:'',render:(r)=><div className="flex justify-end gap-1"><Button size="sm" variant="ghost" onClick={(e)=>{e.stopPropagation();edit(r)}}><Pencil size={13}/>Sửa</Button><RowMenu><button className="danger" onClick={()=>setConfirm(r)}>Xóa nhân viên</button></RowMenu></div>}]
  return <><PageHeader eyebrow="Quản lý" title="Nhân viên" description="Click nhân viên để chỉnh sửa; số khách PT mở danh sách đã lọc." action={<Button onClick={()=>edit(null)}><Plus size={16}/>Thêm nhân viên</Button>}/><div className="toolbar"><SearchInput value={search} onChange={(value)=>{setSearch(value);setPage(1)}} placeholder="Tên, điện thoại, mã nhân viên…"/></div><DataTable columns={columns} rows={query.data?.items} loading={query.isLoading} error={query.error} onRowClick={edit}/><Pagination data={query.data?.pagination} onPage={setPage}/><Modal open={open} onClose={()=>setOpen(false)} title={selected?'Chỉnh sửa nhân viên':'Thêm nhân viên'}><form onSubmit={(e)=>{e.preventDefault();save.mutate(form)}}><div className="modal-body"><div className="form-grid"><Field className="form-span" label="Họ tên" required><Input autoFocus value={form.name} onChange={(e)=>setForm({...form,name:e.target.value})}/></Field><Field label="Điện thoại"><Input value={form.phone} onChange={(e)=>setForm({...form,phone:e.target.value})}/></Field><Field label="Email"><Input type="email" value={form.email} onChange={(e)=>setForm({...form,email:e.target.value})}/></Field><Field className="form-span" label="Chức danh"><Input value={form.title} onChange={(e)=>setForm({...form,title:e.target.value})}/></Field></div>{error&&<div className="inline-error mt-4">{error}</div>}</div><div className="form-actions"><Button variant="secondary" onClick={()=>setOpen(false)}>Hủy</Button><Button type="submit" disabled={save.isPending}>{save.isPending?'Đang lưu…':'Lưu nhân viên'}</Button></div></form></Modal><Modal open={!!confirm} onClose={()=>setConfirm(null)} title="Xóa nhân viên?" description="Nhân viên đã có lịch sử sẽ được ẩn thay vì xóa dữ liệu."><div className="modal-body"><p className="text-[13px] text-slate-600">Bạn đang xóa <strong>{confirm?.name}</strong>. Dữ liệu liên quan sẽ được bảo toàn.</p></div><div className="form-actions"><Button variant="secondary" onClick={()=>setConfirm(null)}>Hủy</Button><Button variant="danger" onClick={()=>remove.mutate(confirm)} disabled={remove.isPending}>Xóa nhân viên</Button></div></Modal></>
}

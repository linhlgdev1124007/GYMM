import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { api } from '../../services/api'
import { PageHeader } from '../../components/common/PageHeader'
import { Button } from '../../components/ui/Button'
import { DataTable } from '../../components/ui/DataTable'
import { Field, Input } from '../../components/ui/Form'
import { Modal } from '../../components/ui/Modal'
import { RowMenu } from '../../components/ui/RowMenu'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { money } from '../../utils/format'

const blank={name:'',category:'Fitness',durationDays:30,price:0}
export function PlansPage(){
  const client=useQueryClient();const[open,setOpen]=useState(false);const[selected,setSelected]=useState(null);const[form,setForm]=useState(blank);const[error,setError]=useState('')
  const query=useQuery({queryKey:['plans'],queryFn:()=>api('/api/plans?includeInactive=true')})
  useEffect(()=>setForm(selected?{name:selected.name,category:selected.category,durationDays:selected.durationDays,price:selected.price}:blank),[selected,open])
  const edit=(row)=>{setSelected(row);setError('');setOpen(true)}
  const save=useMutation({mutationFn:(payload)=>api(selected?`/api/plans/${selected.id}`:'/api/plans',{method:selected?'PATCH':'POST',body:payload}),onSuccess:()=>{client.invalidateQueries({queryKey:['plans']});client.invalidateQueries({queryKey:['member-options']});setOpen(false);setSelected(null);toast.success('Đã lưu gói tập.')},onError:(e)=>setError(e.message)})
  const toggle=useMutation({mutationFn:(row)=>api(`/api/plans/${row.id}`,{method:'PATCH',body:{active:!row.active}}),onSuccess:()=>{client.invalidateQueries({queryKey:['plans']});toast.success('Đã cập nhật trạng thái gói.')}})
  const columns=[{key:'name',label:'Gói tập',render:(r)=><button className="text-left" onClick={(e)=>{e.stopPropagation();edit(r)}}><span className="cell-primary hover:text-blue-700">{r.name}</span><div className="cell-secondary">{r.code}</div></button>},{key:'category',label:'Danh mục'},{key:'duration',label:'Thời hạn',render:(r)=>`${r.durationDays} ngày`},{key:'price',label:'Giá',render:(r)=>money(r.price)},{key:'members',label:'Hội viên hiện tại',className:'text-right',render:(r)=><Link className="font-medium text-blue-700 hover:underline" to={`/members?packageId=${r.id}`} onClick={(e)=>e.stopPropagation()}>{r.memberCount}</Link>},{key:'active',label:'Trạng thái',render:(r)=><StatusBadge status={r.active?'active':'inactive'}/>},{key:'edit',label:'',render:(r)=><div className="flex justify-end gap-1"><Button size="sm" variant="ghost" onClick={(e)=>{e.stopPropagation();edit(r)}}><Pencil size={13}/>Sửa</Button><RowMenu><button onClick={()=>toggle.mutate(r)}>{r.active?'Ngừng sử dụng':'Kích hoạt lại'}</button></RowMenu></div>}]
  return <><PageHeader eyebrow="Quản lý" title="Gói tập" description="Click gói để chỉnh sửa; số hội viên mở trực tiếp danh sách đã lọc." action={<Button onClick={()=>edit(null)}><Plus size={16}/>Thêm gói</Button>}/><DataTable rows={query.data} columns={columns} loading={query.isLoading} error={query.error} onRowClick={edit}/><Modal open={open} onClose={()=>setOpen(false)} title={selected?'Chỉnh sửa gói tập':'Thêm gói tập'}><form onSubmit={(e)=>{e.preventDefault();save.mutate(form)}}><div className="modal-body"><div className="form-grid"><Field className="form-span" label="Tên gói" required><Input autoFocus value={form.name} onChange={(e)=>setForm({...form,name:e.target.value})}/></Field><Field label="Danh mục"><Input value={form.category} onChange={(e)=>setForm({...form,category:e.target.value})}/></Field><Field label="Thời hạn (ngày)"><Input type="number" min="1" value={form.durationDays} onChange={(e)=>setForm({...form,durationDays:Number(e.target.value)})}/></Field><Field label="Giá"><Input type="number" min="0" value={form.price} onChange={(e)=>setForm({...form,price:Number(e.target.value)})}/></Field></div>{error&&<div className="inline-error mt-4">{error}</div>}</div><div className="form-actions"><Button variant="secondary" onClick={()=>setOpen(false)}>Hủy</Button><Button type="submit" disabled={save.isPending}>{save.isPending?'Đang lưu…':'Lưu gói tập'}</Button></div></form></Modal></>
}

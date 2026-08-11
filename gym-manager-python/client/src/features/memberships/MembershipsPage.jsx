import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { api, queryString } from "../../services/api";
import { notify } from "../../services/notify";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { PageHeader } from "../../components/common/PageHeader";
import { SearchInput } from "../../components/common/SearchInput";
import { MembershipForm } from "../../components/forms/MembershipForm";
import { Button } from "../../components/ui/Button";
import { DataTable } from "../../components/ui/DataTable";
import { Modal } from "../../components/ui/Modal";
import { Pagination } from "../../components/ui/Pagination";
import { Select } from "../../components/ui/Form";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { money, shortDate } from "../../utils/format";

export function MembershipsPage() {
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const q = useDebouncedValue(search);
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const [chooseOpen, setChooseOpen] = useState(false);
  const [memberSearch, setMemberSearch] = useState("");
  const memberQ = useDebouncedValue(memberSearch);
  const [selectedMember, setSelectedMember] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (params.get("create") !== "1") return;
    setChooseOpen(true);
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.delete("create");
      return next;
    }, { replace: true });
  }, [params, setParams]);
  const query = useQuery({
    queryKey: ["memberships", q, status, page],
    queryFn: () =>
      api(`/api/memberships?${queryString({ q, status, page, pageSize: 20 })}`),
  });
  const candidates = useQuery({
    queryKey: ["member-candidates", memberQ],
    queryFn: () =>
      api(`/api/members?${queryString({ q: memberQ, pageSize: 10 })}`),
    enabled: chooseOpen && memberQ.length > 1,
  });
  const options = useQuery({
    queryKey: ["member-options"],
    queryFn: () => api("/api/members/options"),
    staleTime: 300000,
  });
  const create = useMutation({
    mutationFn: (data) =>
      api("/api/memberships", { method: "POST", body: data }),
    onSuccess: (data) => {
      client.invalidateQueries({ queryKey: ["memberships"] });
      client.invalidateQueries({ queryKey: ["members"] });
      setFormOpen(false);
      setSelectedMember(null);
      notify.success(
        `Đã đăng ký ${data.package?.name || "gói tập"} cho ${selectedMember.name}.`,
      );
    },
    onError: (e) => setError(e.message),
  });
  const columns = [
    {
      key: "member",
      label: "Hội viên",
      render: (r) => (
        <Link
          className="cell-primary hover:underline"
          to={`/members/${r.memberId}`}
        >
          {r.memberName}
          <div className="cell-secondary">{r.code}</div>
        </Link>
      ),
    },
    { key: "package", label: "Gói tập", render: (r) => r.package.name },
    {
      key: "period",
      label: "Thời hạn",
      render: (r) => `${shortDate(r.startsAt)} → ${shortDate(r.expiresAt)}`,
    },
    { key: "paid", label: "Đã thanh toán", render: (r) => money(r.paidAmount) },
    {
      key: "debt",
      label: "Công nợ",
      render: (r) => (
        <span className={r.debtAmount ? "text-red-700" : ""}>
          {money(r.debtAmount)}
        </span>
      ),
    },
    {
      key: "status",
      label: "Trạng thái",
      render: (r) => <StatusBadge status={r.status} />,
    },
  ];
  return (
    <>
      <PageHeader
        eyebrow="Quản lý"
        title="Đăng ký gói"
        description="Theo dõi thời hạn, thanh toán và công nợ của gói tập thường."
        action={
          <Button onClick={() => setChooseOpen(true)}>
            <Plus size={16} />
            Đăng ký gói
          </Button>
        }
      />
      <div className="toolbar">
        <SearchInput
          value={search}
          onChange={(v) => {
            setSearch(v);
            setPage(1);
          }}
          placeholder="Hội viên, mã đăng ký, tên gói…"
        />
        <Select
          className="input w-44"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
        >
          <option value="all">Tất cả trạng thái</option>
          <option value="active">Hoạt động</option>
          <option value="expiring">Sắp hết hạn</option>
          <option value="expired">Hết hạn</option>
          <option value="frozen">Tạm dừng</option>
        </Select>
      </div>
      <DataTable
        columns={columns}
        rows={query.data?.items}
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        emptyTitle={search || status !== "all" ? "Không có đăng ký phù hợp" : "Chưa có đăng ký gói"}
        emptyDescription={search || status !== "all" ? "Thử từ khóa khác hoặc xóa bộ lọc hiện tại." : "Chọn hội viên để tạo đăng ký gói đầu tiên."}
        emptyAction={
          search || status !== "all" ? (
            <Button size="sm" variant="secondary" onClick={() => { setSearch(""); setStatus("all"); setPage(1); }}>
              Xóa tìm kiếm và bộ lọc
            </Button>
          ) : (
            <Button size="sm" onClick={() => setChooseOpen(true)}>
              <Plus size={14} /> Đăng ký gói
            </Button>
          )
        }
      />
      <Pagination data={query.data?.pagination} onPage={setPage} />
      <Modal
        open={chooseOpen}
        onClose={() => setChooseOpen(false)}
        title="Chọn hội viên"
        description="Tìm theo tên, điện thoại hoặc mã hội viên."
      >
        <div className="modal-body">
          <SearchInput
            value={memberSearch}
            onChange={setMemberSearch}
            placeholder="Nhập ít nhất 2 ký tự…"
          />
          <div className="mt-3 divide-y divide-slate-100 border-y border-slate-200">
            {candidates.data?.items.map((row) => (
              <button
                key={row.id}
                className="flex w-full items-center justify-between px-3 py-3 text-left hover:bg-slate-50"
                onClick={() => {
                  setSelectedMember(row);
                  setChooseOpen(false);
                  setFormOpen(true);
                }}
              >
                <div>
                  <strong className="text-[13px] font-medium">
                    {row.name}
                  </strong>
                  <p className="text-xs text-slate-400">
                    {row.code} · {row.phone}
                  </p>
                </div>
                <span className="text-xs text-navy-700">Chọn</span>
              </button>
            ))}
          </div>
          {memberQ.length > 1 &&
            !candidates.isLoading &&
            !candidates.data?.items.length && (
              <p className="py-8 text-center text-xs text-slate-400">
                Không tìm thấy hội viên phù hợp.
              </p>
            )}
        </div>
      </Modal>
      <MembershipForm
        memberId={selectedMember?.id}
        options={options.data}
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSubmit={(data) => create.mutate(data)}
        pending={create.isPending}
        error={error}
      />
    </>
  );
}

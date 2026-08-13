import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../../services/api";
import { notify } from "../../services/notify";
import { PageHeader } from "../../components/common/PageHeader";
import { Button } from "../../components/ui/Button";
import { DataTable } from "../../components/ui/DataTable";
import { Field, Input } from "../../components/ui/Form";
import { Modal } from "../../components/ui/Modal";
import { MoneyInput, NumberUnitInput } from "../../components/ui/SmartInputs";
import { RowMenu } from "../../components/ui/RowMenu";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { money } from "../../utils/format";

const blank = { name: "", category: "Fitness", durationDays: 30, price: 0 };
const categoryCollator = new Intl.Collator("vi", {
  numeric: true,
  sensitivity: "base",
});

export function PlansPage() {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(null);
  const [tab, setTab] = useState("active");
  const [form, setForm] = useState(blank);
  const [error, setError] = useState("");
  const query = useQuery({
    queryKey: ["plans"],
    queryFn: () => api("/api/plans?includeInactive=true"),
  });
  useEffect(
    () =>
      setForm(
        selected
          ? {
              name: selected.name,
              category: selected.category,
              durationDays: selected.durationDays,
              price: selected.price,
            }
          : blank,
      ),
    [selected, open],
  );
  const edit = (row) => {
    setSelected(row);
    setError("");
    setOpen(true);
  };
  const rows = useMemo(
    () => (query.data || []).filter((row) => (tab === "active" ? row.active : !row.active)),
    [query.data, tab],
  );
  const groupedRows = useMemo(() => {
    const groups = new Map();
    rows.forEach((row) => {
      const category = String(row.category || "Chưa phân loại").trim() || "Chưa phân loại";
      if (!groups.has(category)) groups.set(category, []);
      groups.get(category).push(row);
    });
    return [...groups.entries()]
      .sort(([left], [right]) => categoryCollator.compare(left, right))
      .map(([category, items]) => ({
        category,
        items: [...items].sort((left, right) => {
          const priceDiff = Number(left.price || 0) - Number(right.price || 0);
          return priceDiff || categoryCollator.compare(left.name || "", right.name || "");
        }),
      }));
  }, [rows]);
  const counts = useMemo(
    () => ({
      active: (query.data || []).filter((row) => row.active).length,
      inactive: (query.data || []).filter((row) => !row.active).length,
    }),
    [query.data],
  );
  const save = useMutation({
    mutationFn: (payload) =>
      api(selected ? `/api/plans/${selected.id}` : "/api/plans", {
        method: selected ? "PATCH" : "POST",
        body: payload,
      }),
    onSuccess: (data) => {
      client.invalidateQueries({ queryKey: ["plans"] });
      client.invalidateQueries({ queryKey: ["member-options"] });
      setOpen(false);
      setSelected(null);
      notify.success(
        selected
          ? `Đã lưu thay đổi cho gói ${data.name || selected.name}.`
          : `Đã tạo gói tập ${data.name}.`,
      );
    },
    onError: (e) => setError(e.message),
  });
  const toggle = useMutation({
    mutationFn: (row) =>
      api(`/api/plans/${row.id}`, {
        method: "PATCH",
        body: { active: !row.active },
      }),
    onSuccess: (data, row) => {
      client.invalidateQueries({ queryKey: ["plans"] });
      notify.success(
        `${data.active ? "Đã kích hoạt" : "Đã tạm ngừng"} gói ${row.name}.`,
      );
    },
    onError: (e) =>
      notify.errorFrom(e, "Không thể đổi trạng thái gói. Vui lòng thử lại."),
  });
  const remove = useMutation({
    mutationFn: (row) => api(`/api/plans/${row.id}`, { method: "DELETE" }),
    onSuccess: (_, row) => {
      client.invalidateQueries({ queryKey: ["plans"] });
      client.invalidateQueries({ queryKey: ["member-options"] });
      notify.success(`Đã xóa gói ${row.name}.`);
    },
    onError: (e) =>
      notify.errorFrom(e, "Không thể xóa gói. Vui lòng thử lại."),
  });
  const handleDelete = (row) => {
    const confirmed = window.confirm(
      `Xóa gói "${row.name}"?\n\nChỉ xóa được gói chưa từng có hội viên đăng ký.`,
    );
    if (confirmed) remove.mutate(row);
  };
  const columns = [
    {
      key: "name",
      label: "Gói tập",
      render: (r) => (
        <button
          className="text-left"
          onClick={(e) => {
            e.stopPropagation();
            edit(r);
          }}
        >
          <span className="cell-primary hover:text-blue-700">{r.name}</span>
          <div className="cell-secondary">{r.code}</div>
        </button>
      ),
    },
    {
      key: "duration",
      label: "Thời hạn",
      render: (r) => `${r.durationDays} ngày`,
    },
    { key: "price", label: "Giá", render: (r) => money(r.price) },
    {
      key: "members",
      label: "Hội viên hiện tại",
      className: "text-right",
      render: (r) => (
        <Link
          className="font-medium text-blue-700 hover:underline"
          to={`/members?packageId=${r.id}`}
          onClick={(e) => e.stopPropagation()}
        >
          {r.memberCount}
        </Link>
      ),
    },
    {
      key: "active",
      label: "Trạng thái",
      render: (r) => <StatusBadge status={r.active ? "active" : "inactive"} />,
    },
    {
      key: "actions",
      label: "",
      render: (r) => (
        <div className="flex justify-end gap-1">
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              edit(r);
            }}
          >
            <Pencil size={13} />
            Sửa
          </Button>
          <RowMenu>
            <button onClick={() => toggle.mutate(r)}>
              {r.active ? "Ngừng sử dụng" : "Kích hoạt lại"}
            </button>
            {r.canDelete && (
              <button className="danger" onClick={() => handleDelete(r)}>
                <Trash2 size={13} />
                Xóa gói
              </button>
            )}
          </RowMenu>
        </div>
      ),
    },
  ];
  return (
    <>
      <PageHeader
        eyebrow="Quản lý"
        title="Gói tập"
        description="Click gói để chỉnh sửa; số hội viên mở trực tiếp danh sách đã lọc."
        action={
          <Button onClick={() => edit(null)}>
            <Plus size={16} />
            Thêm gói
          </Button>
        }
      />
      <div className="tabs mb-4">
        <button
          className={`tab ${tab === "active" ? "active" : ""}`}
          onClick={() => setTab("active")}
        >
          Gói đang hoạt động ({counts.active})
        </button>
        <button
          className={`tab ${tab === "inactive" ? "active" : ""}`}
          onClick={() => setTab("inactive")}
        >
          Gói inactive ({counts.inactive})
        </button>
      </div>
      {query.isLoading || query.error || !groupedRows.length ? (
        <DataTable
          rows={[]}
          columns={columns}
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          onRowClick={edit}
          emptyTitle={tab === "active" ? "Không có gói đang hoạt động" : "Không có gói inactive"}
          emptyDescription={tab === "active" ? "Tạo gói mới để bắt đầu bán cho hội viên." : "Gói tạm ngừng sử dụng sẽ xuất hiện tại đây."}
        />
      ) : (
        <div className="space-y-7">
          {groupedRows.map((group) => (
            <section key={group.category}>
              <div className="section-header">
                <div>
                  <h2>{group.category}</h2>
                  <p>{group.items.length} gói</p>
                </div>
              </div>
              <DataTable
                rows={group.items}
                columns={columns}
                onRowClick={edit}
                emptyTitle={`Không có gói ${group.category}`}
                emptyDescription="Gói thuộc danh mục này sẽ xuất hiện tại đây."
              />
            </section>
          ))}
        </div>
      )}
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        dirty={
          JSON.stringify(form) !==
          JSON.stringify(
            selected
              ? {
                  name: selected.name,
                  category: selected.category,
                  durationDays: selected.durationDays,
                  price: selected.price,
                }
              : blank,
          )
        }
        title={selected ? "Chỉnh sửa gói tập" : "Thêm gói tập"}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate({
              ...form,
              name: form.name.trim(),
              category: form.category.trim(),
            });
          }}
        >
          <div className="modal-body">
            <div className="form-grid">
              <Field className="form-span" label="Tên gói" required>
                <Input
                  autoFocus
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </Field>
              <Field label="Danh mục">
                <Input
                  value={form.category}
                  onChange={(e) =>
                    setForm({ ...form, category: e.target.value })
                  }
                />
              </Field>
              <Field label="Thời hạn">
                <NumberUnitInput
                  min="1"
                  unit="ngày"
                  value={form.durationDays}
                  onChange={(durationDays) =>
                    setForm({ ...form, durationDays: Number(durationDays) })
                  }
                />
              </Field>
              <Field label="Giá">
                <MoneyInput
                  min="0"
                  value={form.price}
                  onChange={(price) => setForm({ ...form, price })}
                />
              </Field>
            </div>
            {error && <div className="inline-error mt-4">{error}</div>}
          </div>
          <div className="form-actions">
            <Button
              data-modal-close
              variant="secondary"
              onClick={() => setOpen(false)}
            >
              Hủy
            </Button>
            <Button
              type="submit"
              loading={save.isPending}
              loadingText="Đang lưu…"
            >
              Lưu gói tập
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}

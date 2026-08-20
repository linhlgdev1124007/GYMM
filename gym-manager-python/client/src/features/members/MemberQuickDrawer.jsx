import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarPlus,
  CreditCard,
  Dumbbell,
  ExternalLink,
  Pencil,
  ScanFace,
  TriangleAlert,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../../services/api";
import { notify } from "../../services/notify";
import {
  dateTime,
  formatPhone,
  initials,
  money,
  shortDate,
} from "../../utils/format";
import { Drawer } from "../../components/ui/Drawer";
import { Button } from "../../components/ui/Button";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { ScheduleSummary } from "../../components/ui/ScheduleSummary";
import { InlineEditField } from "../../components/ui/InlineEditField";
import { MembershipTimeline } from "../../components/ui/MembershipTimeline";
import { RowMenu } from "../../components/ui/RowMenu";
import { MemberEditForm } from "../../components/forms/MemberEditForm";
import { MembershipForm } from "../../components/forms/MembershipForm";
import { MembershipOperationsModal } from "../../components/forms/MembershipOperationsModal";
import { MembershipFreezeForm } from "../../components/forms/MembershipFreezeForm";
import { TrainingForm } from "../../components/forms/TrainingForm";
import { QuickPaymentForm } from "../../components/forms/QuickPaymentForm";
import { DebtDeadlineForm } from "../../components/forms/DebtDeadlineForm";
import { useAuth } from "../../app/AuthContext";
import { DahIdentityDeleteModal } from "./DahIdentityDeleteModal";
import { DahIdentityLinkModal } from "./DahIdentityLinkModal";

export function MemberQuickDrawer({
  memberId,
  onClose,
  initialAction,
  onActionConsumed,
}) {
  const { user } = useAuth();
  const canFinancial = ["admin", "manager", "receptionist"].includes(
    user?.role,
  );
  const canManageLifecycle = ["admin", "manager"].includes(user?.role);
  const client = useQueryClient();
  const [dialog, setDialog] = useState(null);
  const [membershipOperationAction, setMembershipOperationAction] = useState("");
  const [selectedFreeze, setSelectedFreeze] = useState(null);
  const [identityLinkOpen, setIdentityLinkOpen] = useState(false);
  const [identityDeleteOpen, setIdentityDeleteOpen] = useState(false);
  const [formError, setFormError] = useState("");
  const memberQuery = useQuery({
    queryKey: ["member", memberId],
    queryFn: () => api(`/api/members/${memberId}`),
    enabled: !!memberId,
  });
  const options = useQuery({
    queryKey: ["member-options"],
    queryFn: () => api("/api/members/options"),
    staleTime: 300000,
  });
  const member = memberQuery.data;
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["member", memberId] });
    client.invalidateQueries({ queryKey: ["members"] });
    client.invalidateQueries({ queryKey: ["memberships"] });
    client.invalidateQueries({ queryKey: ["training"] });
    client.invalidateQueries({ queryKey: ["payments"] });
    client.invalidateQueries({ queryKey: ["reports"] });
    client.invalidateQueries({ queryKey: ["dashboard"] });
  };
  const update = useMutation({
    mutationFn: ({ payload }) =>
      api(`/api/members/${memberId}`, { method: "PATCH", body: payload }),
    onSuccess: (_data, variables) => {
      refresh();
      if (!variables.silent) {
        setDialog(null);
        notify.success(`Đã lưu hồ sơ ${member.name}.`);
      }
    },
    onError: (e, variables) => {
      if (!variables.silent) setFormError(e.message);
    },
  });
  const membershipSave = useMutation({
    mutationFn: ({ id, data }) =>
      api(id ? `/api/memberships/${id}` : "/api/memberships", {
        method: id ? "PATCH" : "POST",
        body: data,
      }),
    onSuccess: (_data, variables) => {
      refresh();
      setDialog(null);
      if (variables.feedback?.amount) {
        notify.success(
          `Đã ghi nhận ${money(variables.feedback.amount)} cho ${member.name}.`,
        );
      } else if (variables.feedback?.expiresAt) {
        notify.success(
          `Đã lưu ${variables.feedback.planName} đến ${shortDate(variables.feedback.expiresAt)} cho ${member.name}.`,
        );
      } else {
        notify.success(`Đã cập nhật gói tập của ${member.name}.`);
      }
    },
    onError: (e) => setFormError(e.message),
  });
  const deadlineSave = useMutation({
    mutationFn: (payload) =>
      api(`/api/memberships/${current.id}/debt-due-date`, {
        method: "PATCH",
        body: payload,
      }),
    onSuccess: () => {
      refresh();
      setDialog(null);
      notify.success(`Đã lưu hạn thanh toán cho ${member.name}.`);
    },
    onError: (e) => setFormError(e.message),
  });
  const trainingSave = useMutation({
    mutationFn: ({ id, payload }) =>
      api(id ? `/api/training/${id}` : `/api/members/${memberId}/training`, {
        method: id ? "PATCH" : "POST",
        body: payload,
      }),
    onSuccess: () => {
      refresh();
      setDialog(null);
      notify.success(`Đã cập nhật đăng ký PT của ${member.name}.`);
    },
    onError: (e) => setFormError(e.message),
  });
  const membershipOperation = useMutation({
    mutationFn: ({ action, membershipId, payload }) =>
      api(
        action === "freeze"
          ? `/api/memberships/${current.id}/freeze`
          : `/api/memberships/${membershipId || current.id}/actions`,
        { method: "POST", body: payload },
      ),
    onSuccess: (result, variables) => {
      refresh();
      setDialog(null);
      setMembershipOperationAction("");
      notify.success(variables.action === "freeze" ? "Đã bảo lưu và cộng bù thời hạn gói." : result.summary);
    },
    onError: (e) => setFormError(e.message),
  });
  const freezeMutation = useMutation({
    mutationFn: ({ freezeId, payload, method }) =>
      api(`/api/memberships/${current.id}/freezes/${freezeId}`, {
        method,
        body: method === "DELETE" ? undefined : payload,
      }),
    onSuccess: (_result, variables) => {
      refresh();
      setDialog(null);
      setSelectedFreeze(null);
      notify.success(variables.method === "DELETE" ? "Đã hủy lịch bảo lưu." : "Đã cập nhật lịch bảo lưu.");
    },
    onError: (e) => setFormError(e.message),
  });
  const current = member?.memberships[0];
  const displayStatus = current?.status || member?.status;
  const training = member?.training.find((row) => row.status === "active");
  const trainingCoaches = training?.coaches || [];
  const lastCheckin = member?.checkins[0];
  const daysLeft = current?.expiresAt
    ? Math.ceil((new Date(current.expiresAt) - new Date()) / 86400000)
    : null;
  const openDialog = (name, operationAction = "") => {
    setFormError("");
    setMembershipOperationAction(name === "operations" ? operationAction : "");
    setDialog(name);
  };
  const openFreezeEdit = (freeze) => {
    setFormError("");
    setSelectedFreeze(freeze);
    setDialog("freeze-edit");
  };
  const deleteFreeze = (freeze) => {
    if (!window.confirm(`Hủy lịch bảo lưu ${shortDate(freeze.startsAt)} → ${shortDate(freeze.endsAt)}?`)) return;
    setFormError("");
    freezeMutation.mutate({ freezeId: freeze.id, method: "DELETE" });
  };
  const lifecycleActions = [];
  if (current?.status === "pending") {
    lifecycleActions.push(["activate", "Kích hoạt ngay"]);
  }
  if (current?.status === "suspended") {
    lifecycleActions.push(["activate", "Kích hoạt lại"]);
  }
  if (current?.status === "frozen") {
    lifecycleActions.push(["activate", "Kích hoạt lại"]);
  }
  if (current?.status === "active") {
    lifecycleActions.push(["suspend", "Tạm dừng"]);
    lifecycleActions.push(["freeze", "Bảo lưu"]);
  }
  if (current?.status === "expired") {
    lifecycleActions.push(["freeze", "Bảo lưu"]);
  }
  if (["active", "expired"].includes(current?.status)) {
    lifecycleActions.push(["adjust_days", "Cộng / trừ ngày"]);
  }
  useEffect(() => {
    if (member && initialAction) {
      openDialog(initialAction);
      onActionConsumed?.();
    }
  }, [member, initialAction, onActionConsumed]);
  useEffect(() => {
    if (!memberId) {
      setDialog(null);
      setIdentityLinkOpen(false);
    }
  }, [memberId]);
  return (
    <>
      <Drawer
        open={!!memberId}
        onClose={onClose}
        title={member?.name || "Thông tin hội viên"}
        description={
          member
            ? `${member.code} · ${member.phone || "Chưa có số điện thoại"}`
            : "Đang tải…"
        }
        footer={
          member && (
            <>
              <span className="text-xs text-slate-400">
                Thông tin chi tiết và lịch sử
              </span>
              <Link
                className="inline-flex items-center gap-1 text-xs font-medium text-navy-800 hover:underline"
                to={`/members/${member.id}`}
                data-member-full-profile="true"
              >
                Xem hồ sơ đầy đủ <ExternalLink size={12} />
              </Link>
            </>
          )
        }
      >
        {memberQuery.isLoading && (
          <div className="space-y-4 p-5">
            <div className="skeleton h-16" />
            <div className="skeleton h-48" />
            <div className="skeleton h-32" />
          </div>
        )}
        {memberQuery.isError && (
          <div className="m-5 inline-error">{memberQuery.error.message}</div>
        )}
        {member && (
          <>
            <div className="flex items-center gap-3 border-b border-slate-200 px-5 py-4">
              <div className="avatar h-11 w-11">
                {member.avatarImageData ? (
                  <img src={member.avatarImageData} alt="" />
                ) : (
                  initials(member.name)
                )}
              </div>
              <div className="min-w-0 flex-1">
                <strong className="block truncate text-[15px] font-semibold text-slate-950">
                  {member.name}
                </strong>
                <span className="text-xs text-slate-400">{member.code}</span>
              </div>
              <StatusBadge status={displayStatus} />
            </div>
            {canFinancial && <div className="quick-action-bar">
              <button
                className="quick-action"
                onClick={() => openDialog("edit")}
              >
                <Pencil size={17} />
                <span>Sửa hồ sơ</span>
              </button>
              <button
                className="quick-action"
                onClick={() =>
                  current?.debtAmount
                    ? openDialog("payment")
                    : notify.info("Hội viên hiện không có công nợ.")
                }
              >
                <CreditCard size={17} />
                <span>Thu tiền</span>
              </button>
              <button
                className="quick-action"
                onClick={() => openDialog("renew")}
              >
                <CalendarPlus size={17} />
                <span>Gia hạn</span>
              </button>
              <button
                className="quick-action"
                onClick={() => openDialog("training")}
              >
                <Dumbbell size={17} />
                <span>{training ? "Đổi nhóm PT" : "Gán nhóm PT"}</span>
              </button>
              {canManageLifecycle && current && lifecycleActions.length > 0 && (
                <RowMenu>
                  {lifecycleActions.map(([action, label]) => (
                    <button key={action} onClick={() => openDialog("operations", action)}>
                      {label}
                    </button>
                  ))}
                </RowMenu>
              )}
            </div>}
            <section className="detail-section">
              {daysLeft != null && daysLeft <= 14 && (
                <div className="detail-alert">
                  <span className="flex items-center gap-2">
                    <TriangleAlert size={15} />
                    Gói{" "}
                    {daysLeft < 0
                      ? "đã hết hạn"
                      : `hết hạn sau ${daysLeft} ngày`}
                  </span>
                  {canFinancial && <button onClick={() => openDialog("renew")}>Gia hạn</button>}
                </div>
              )}
              {current?.debtAmount > 0 && (
                <div className="detail-alert debt">
                  <span className="flex items-center gap-2">
                    <TriangleAlert size={15} />
                    Công nợ {money(current.debtAmount)}
                  </span>
                  {canFinancial && <button onClick={() => openDialog("payment")}>
                    Thu tiền
                  </button>}
                </div>
              )}
              {!training && (
                <div className="detail-alert">
                  <span className="flex items-center gap-2">
                    <TriangleAlert size={15} />
                    Chưa đăng ký PT
                  </span>
                  {canFinancial && <button onClick={() => openDialog("training")}>
                    Đăng ký PT
                  </button>}
                </div>
              )}
              {training && !trainingCoaches.length && (
                <div className="detail-alert">
                  <span className="flex items-center gap-2">
                    <TriangleAlert size={15} />
                    Đăng ký PT chưa có Coach
                  </span>
                  <button onClick={() => openDialog("training")}>
                    Phân công
                  </button>
                </div>
              )}
              <h3 className="detail-section-title">Gói tập</h3>
              {current ? (
                <>
                  <dl>
                    <div className="inline-field">
                      <dt>Gói hiện tại</dt>
                      <dd className="font-medium">{current.package.name}</dd>
                    </div>
                    <div className="inline-field">
                      <dt>Thời hạn</dt>
                      <dd>
                        {shortDate(current.startsAt)} →{" "}
                        {shortDate(current.expiresAt)}
                      </dd>
                    </div>
                    <div className="inline-field">
                      <dt>Còn lại</dt>
                      <dd>
                        {daysLeft == null
                          ? "—"
                          : daysLeft < 0
                            ? `Quá hạn ${Math.abs(daysLeft)} ngày`
                            : `${daysLeft} ngày`}
                      </dd>
                    </div>
                    <div className="inline-field">
                      <dt>Đã thanh toán</dt>
                      <dd>{money(current.paidAmount)}</dd>
                    </div>
                    <div className="inline-field">
                      <dt>Công nợ</dt>
                      <dd
                        className={
                          current.debtAmount
                            ? "font-medium text-red-700"
                            : "text-emerald-700"
                        }
                      >
                        {money(current.debtAmount)}
                        {canFinancial && current.debtAmount > 0 && (
                          <button
                            className="ml-3 text-xs font-medium text-blue-700"
                            onClick={() => openDialog("payment")}
                          >
                            Thu tiền
                          </button>
                        )}
                      </dd>
                    </div>
                    {current.debtAmount > 0 && (
                      <div className="inline-field">
                        <dt>Hạn thanh toán</dt>
                        <dd>
                          {canFinancial ? <button
                            className={
                              current.debtDueDate &&
                              new Date(`${current.debtDueDate}T23:59:59`) <
                                new Date()
                                ? "font-medium text-red-700 hover:underline"
                                : "font-medium text-blue-700 hover:underline"
                            }
                            onClick={() => openDialog("deadline")}
                          >
                            {current.debtDueDate
                              ? `${shortDate(current.debtDueDate)} · Đổi hạn`
                              : "+ Đặt hạn"}
                          </button> : (current.debtDueDate ? shortDate(current.debtDueDate) : "Chưa đặt hạn")}
                        </dd>
                      </div>
                    )}
                  </dl>
                  <MembershipTimeline membership={current} compact onEditFreeze={canManageLifecycle ? openFreezeEdit : undefined} onDeleteFreeze={canManageLifecycle ? deleteFreeze : undefined} />
                </>
              ) : (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-400">Chưa có gói tập</span>
                  {canFinancial && <Button size="sm" onClick={() => openDialog("renew")}>
                    Đăng ký gói
                  </Button>}
                </div>
              )}
            </section>
            <section className="detail-section">
              <h3 className="detail-section-title">Vận hành</h3>
              <dl>
                <div className="inline-field">
                  <dt>Check-in gần nhất</dt>
                  <dd>
                    {lastCheckin
                      ? dateTime(lastCheckin.checkedInAt)
                      : "Chưa có"}
                  </dd>
                </div>
                <div className="inline-field">
                  <dt>Check-in gần đây</dt>
                  <dd>{member.checkins.length} lượt được ghi nhận</dd>
                </div>
                <div className="inline-field">
                  <dt>PT hiện tại</dt>
                  <dd>
                    {training ? (
                      <>
                        {training.packageName || training.type}
                        <small className="block text-xs text-slate-500">{training.type}</small>
                      </>
                    ) : canFinancial ? (
                      <button
                        className="text-xs font-medium text-blue-700"
                        onClick={() => openDialog("training")}
                      >
                        + Gán nhóm PT
                      </button>
                    ) : "Chưa đăng ký"}
                  </dd>
                </div>
                {training && (
                  <div className="inline-field">
                    <dt>Tài chính PT</dt>
                    <dd>
                      {money(training.paidAmount)} / {money(training.finalPrice)}
                      <small className={`block text-xs ${training.debtAmount > 0 ? "text-red-700" : "text-emerald-700"}`}>
                        {training.debtAmount > 0 ? `${money(training.debtAmount)} nợ${training.nextDebtDueDate ? ` · hạn ${shortDate(training.nextDebtDueDate)}` : ""}` : "Đã tất toán"}
                      </small>
                    </dd>
                  </div>
                )}
                <div className="inline-field">
                  <dt>Lịch PT</dt>
                  <dd>
                    {training
                      ? (
                        <ScheduleSummary
                          schedule={training.schedule}
                          scheduleDays={training.scheduleDays}
                          scheduleTime={training.scheduleTime}
                          emptyText="Chưa chọn thứ"
                          compact
                        />
                      )
                      : "—"}
                  </dd>
                </div>
              </dl>
            </section>
            <section className="detail-section">
              <h3 className="detail-section-title">Liên hệ & phụ trách</h3>
              <dl>
                {canFinancial ? (
                  <>
                    <InlineEditField label="Điện thoại" value={member.phone} type="tel" displayValue={formatPhone(member.phone)} onSave={(phone) => update.mutateAsync({ payload: { phone }, silent: true })} pending={update.isPending} />
                    <InlineEditField label="Email" value={member.email} type="email" emptyAction="+ Thêm email" onSave={(email) => update.mutateAsync({ payload: { email }, silent: true })} pending={update.isPending} />
                    <InlineEditField label="Nguồn khách" value={member.source} onSave={(source) => update.mutateAsync({ payload: { source }, silent: true })} pending={update.isPending} />
                    <div className="inline-field"><dt>Sale phụ trách</dt><dd>{member.salesEmployee || "Chưa gán"}</dd></div>
                    <div className="inline-field">
                      <dt>Định danh DAH</dt>
                        <dd>
                          {member.personUuid ? (
                            <span className="inline-flex items-center gap-2">
                              <span className="font-mono text-[12px]">{member.personUuid}</span>
                              <button className="inline-flex items-center gap-1 text-xs font-medium text-blue-700" onClick={() => setIdentityLinkOpen(true)}>
                                <ScanFace size={13} /> Gán lại
                              </button>
                              <button className="inline-flex items-center gap-1 text-xs font-medium text-red-700" onClick={() => setIdentityDeleteOpen(true)}>
                                Xóa
                              </button>
                            </span>
                          ) : (
                          <button className="inline-flex items-center gap-1 text-xs font-medium text-blue-700" onClick={() => setIdentityLinkOpen(true)}>
                            <ScanFace size={13} /> Liên kết định danh
                          </button>
                        )}
                      </dd>
                    </div>
                    <div className="inline-field"><dt>Trạng thái hồ sơ</dt><dd><StatusBadge status={displayStatus} /></dd></div>
                  </>
                ) : (
                  <>
                    <div className="inline-field"><dt>Điện thoại</dt><dd>{formatPhone(member.phone) || "—"}</dd></div>
                    <div className="inline-field"><dt>Email</dt><dd>{member.email || "—"}</dd></div>
                    <div className="inline-field"><dt>Nguồn khách</dt><dd>{member.source || "—"}</dd></div>
                    <div className="inline-field"><dt>Sale phụ trách</dt><dd>{member.salesEmployee || "Chưa gán"}</dd></div>
                    <div className="inline-field"><dt>Định danh DAH</dt><dd>{member.personUuid || "Chưa liên kết"}</dd></div>
                    <div className="inline-field"><dt>Trạng thái hồ sơ</dt><dd><StatusBadge status={member.status} /></dd></div>
                  </>
                )}
              </dl>
            </section>
            {member.notes && (
              <section className="detail-section">
                <h3 className="detail-section-title">
                  Ghi chú quan trọng{" "}
                  {canFinancial && <button
                    className="normal-case text-blue-700"
                    onClick={() => openDialog("edit")}
                  >
                    Chỉnh sửa
                  </button>}
                </h3>
                <p className="text-[13px] leading-5 text-slate-700">
                  {member.notes}
                </p>
              </section>
            )}
          </>
        )}
      </Drawer>
      {member && (
        <>
          <MemberEditForm
            member={member}
            options={options.data}
            open={dialog === "edit"}
            onClose={() => setDialog(null)}
            onSubmit={(payload) => update.mutate({ payload })}
            pending={update.isPending}
            error={formError}
          />
          <MembershipForm
            memberId={member.id}
            member={member}
            currentMembership={current}
            options={options.data}
            open={dialog === "renew"}
            onClose={() => setDialog(null)}
            onSubmit={(data, feedback) =>
              membershipSave.mutate({ data, feedback })
            }
            pending={membershipSave.isPending}
            error={formError}
          />
          <QuickPaymentForm
            membership={current}
            options={options.data}
            open={dialog === "payment"}
            onClose={() => setDialog(null)}
            onSubmit={(data, feedback) =>
              membershipSave.mutate({ id: current.id, data, feedback })
            }
            pending={membershipSave.isPending}
            error={formError}
          />
          <DebtDeadlineForm
            membership={current}
            open={dialog === "deadline"}
            onClose={() => setDialog(null)}
            onSubmit={(payload) => deadlineSave.mutate(payload)}
            pending={deadlineSave.isPending}
            error={formError}
          />
          <MembershipOperationsModal
            membership={current}
            memberships={member.memberships}
            memberId={member.id}
            options={options.data}
            open={dialog === "operations"}
            initialAction={membershipOperationAction}
            onClose={() => {
              setDialog(null);
              setMembershipOperationAction("");
            }}
            onSubmit={(variables) => membershipOperation.mutate(variables)}
            pending={membershipOperation.isPending}
            error={formError}
          />
          <MembershipFreezeForm
            membership={current}
            freeze={selectedFreeze}
            open={dialog === "freeze-edit"}
            onClose={() => {
              setDialog(null);
              setSelectedFreeze(null);
            }}
            onSubmit={(payload) => freezeMutation.mutate({ freezeId: selectedFreeze.id, method: "PATCH", payload })}
            pending={freezeMutation.isPending}
            error={formError}
          />
          <TrainingForm
            enrollment={training}
            options={options.data}
            open={dialog === "training"}
            onClose={() => setDialog(null)}
            onSubmit={(payload) =>
              trainingSave.mutate({ id: training?.id, payload })
            }
            pending={trainingSave.isPending}
            error={formError}
          />
          <DahIdentityLinkModal
            open={identityLinkOpen}
              onClose={() => setIdentityLinkOpen(false)}
              memberId={member.id}
              memberName={member.name}
              currentPersonUuid={member.personUuid}
              currentAvatarImageData={member.avatarImageData}
              onLinked={() => {
                refresh();
                notify.success(`Đã cập nhật định danh DAH cho ${member.name}.`);
              }}
            />
          <DahIdentityDeleteModal
            open={identityDeleteOpen}
            onClose={() => setIdentityDeleteOpen(false)}
            memberId={member.id}
            memberName={member.name}
            personUuid={member.personUuid}
            onDeleted={() => {
              refresh();
              notify.success(`Đã xóa FaceID của ${member.name}.`);
            }}
          />
        </>
      )}
    </>
  );
}

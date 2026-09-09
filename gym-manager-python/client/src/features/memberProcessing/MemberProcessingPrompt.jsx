import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { AlertTriangle, CheckCircle2, Dumbbell, UserRound } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "../../components/ui/Button";
import { Field, Input, Select } from "../../components/ui/Form";
import { Modal } from "../../components/ui/Modal";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { api } from "../../services/api";
import { notify } from "../../services/notify";
import { dateTime, formatPhone, shortDate } from "../../utils/format";

function avatarText(name = "") {
  return (
    name
      .trim()
      .split(/\s+/)
      .slice(-2)
      .map((part) => part[0])
      .join("")
      .toUpperCase() || "HV"
  );
}

function localDate(value = new Date()) {
  return format(value instanceof Date ? value : parseISO(value), "yyyy-MM-dd");
}

function localDateTime(value = new Date()) {
  return format(value instanceof Date ? value : parseISO(value), "yyyy-MM-dd'T'HH:mm");
}

function slotText(slots = []) {
  return slots.map((slot) => `${slot.day} ${slot.time}`).join(", ") || "Hôm nay";
}

function ptEnrollments(item) {
  return item?.ptEnrollments || item?.ptToday || [];
}

function QueueRow({ item, selected, pendingKey, onRegular, onSelectPt }) {
  const pt = ptEnrollments(item)[0];
  const pendingPt = pendingKey === `${item.sessionId}:pt`;
  const pendingRegular = pendingKey === `${item.sessionId}:regular`;
  return (
    <article className={`processing-modal-row ${selected ? "selected" : ""}`}>
      <Link to={`/members/${item.member.id}`} className="processing-modal-member">
        <div className="avatar avatar-md">
          {item.member.avatarImageData ? (
            <img src={item.member.avatarImageData} alt="" />
          ) : (
            avatarText(item.member.name)
          )}
        </div>
        <div className="min-w-0">
          <div>
            <UserRound size={15} />
            <strong>{item.member.name}</strong>
          </div>
          <p>
            {item.member.code} · {formatPhone(item.member.phone) || "Chưa có SĐT"} · vào{" "}
            {format(parseISO(item.checkedInAt), "HH:mm")}
          </p>
        </div>
      </Link>
      <div className={`processing-modal-plan ${item.gymDanger ? "danger" : ""}`}>
        <div>
          <span>{item.gymMembership?.package?.name || "Chưa có gói"}</span>
          <StatusBadge status={item.gymMembership?.status || "blocked"} />
        </div>
        <p>
          Hạn {shortDate(item.gymMembership?.expiresAt)}
          {item.gymDangerReason ? ` · ${item.gymDangerReason}` : ""}
        </p>
      </div>
      <div className="processing-modal-pt">
        <strong>
          {pt ? `${pt.type}${pt.todaySlots?.length ? ` · ${slotText(pt.todaySlots)}` : ""}` : "Không có PT"}
        </strong>
        <span>
          {pt
            ? `Còn ${pt.remainingSessions}/${pt.totalSessions} buổi · ${
                pt.coaches?.map((coach) => coach.name).join(", ") || "Chưa phân Coach"
              }`
            : "Không cần xử lý"}
        </span>
      </div>
      <div className="processing-modal-actions">
        <Button
          size="sm"
          variant="primary"
          loading={pendingPt}
          loadingText="Đang trừ..."
          disabled={!pt || pendingRegular}
          onClick={() => onSelectPt(item)}
        >
          <CheckCircle2 size={14} /> Tập PT
        </Button>
        <Button
          size="sm"
          variant="secondary"
          loading={pendingRegular}
          loadingText="Đang lưu..."
          disabled={pendingPt}
          onClick={() => onRegular(item)}
        >
          Tập Thường
        </Button>
      </div>
    </article>
  );
}

export function MemberProcessingPrompt({ open, onClose, query }) {
  const client = useQueryClient();
  const [selectedItem, setSelectedItem] = useState(null);
  const [ptForm, setPtForm] = useState({
    ptEnrollmentId: "",
    trainingDate: localDate(),
    startedAt: localDateTime(),
    endedAt: localDateTime(),
  });
  const items = query.data?.items || [];
  const total = query.data?.pagination?.total || 0;
  const selectedOptions = useMemo(() => ptEnrollments(selectedItem), [selectedItem]);
  const selectedPt =
    selectedOptions.find((row) => String(row.id) === String(ptForm.ptEnrollmentId)) ||
    selectedOptions[0];
  const decision = useMutation({
    mutationFn: ({ item, decision: choice, ptEnrollmentId, trainingDate, startedAt, endedAt }) =>
      api(`/api/member-processing/${item.sessionId}`, {
        method: "POST",
        body: { decision: choice, ptEnrollmentId, trainingDate, startedAt, endedAt },
      }),
    onSuccess: (_data, variables) => {
      setSelectedItem(null);
      client.invalidateQueries({ queryKey: ["member-processing"] });
      client.invalidateQueries({ queryKey: ["training"] });
      client.invalidateQueries({ queryKey: ["checkins"] });
      query.refetch();
      notify.success(
        variables.decision === "pt"
          ? "Đã ghi nhận tập PT và trừ 1 buổi."
          : "Đã ghi nhận tập thường.",
      );
    },
    onError: (error) => notify.errorFrom(error, "Không thể xử lý lượt check-in này."),
  });
  const pendingKey = decision.isPending
    ? `${decision.variables.item.sessionId}:${decision.variables.decision}`
    : null;
  const openPtForm = (item) => {
    const options = ptEnrollments(item);
    const now = new Date();
    setPtForm({
      ptEnrollmentId: options[0]?.id || "",
      trainingDate: localDate(),
      startedAt: localDateTime(now),
      endedAt: localDateTime(new Date(now.getTime() + 60 * 60 * 1000)),
    });
    setSelectedItem(item);
  };
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Hội viên PT cần xử lý"
      description={`${total} lượt check-in đang chờ phân loại Tập PT hoặc Tập Thường`}
      size="xl"
      className="member-processing-prompt"
    >
      <div className="modal-body">
        {query.error ? (
          <div className="processing-modal-error">
            <AlertTriangle size={17} />
            <span>{query.error.message}</span>
          </div>
        ) : query.isLoading ? (
          <div className="space-y-3">
            <div className="skeleton h-20 w-full" />
            <div className="skeleton h-20 w-full" />
          </div>
        ) : items.length ? (
          <div className="processing-modal-list">
            {items.map((item) => (
              <QueueRow
                key={item.sessionId}
                item={item}
                selected={selectedItem?.sessionId === item.sessionId}
                pendingKey={pendingKey}
                onRegular={(row) => decision.mutate({ item: row, decision: "regular" })}
                onSelectPt={openPtForm}
              />
            ))}
          </div>
        ) : (
          <div className="processing-modal-empty">
            <Dumbbell size={32} />
            <strong>Không còn hội viên cần xử lý</strong>
            <span>Queue sẽ tự cập nhật khi có lượt check-in PT mới.</span>
          </div>
        )}
        {selectedItem && (
          <form
            className="processing-modal-pt-form"
            onSubmit={(event) => {
              event.preventDefault();
              decision.mutate({
                item: selectedItem,
                decision: "pt",
                ptEnrollmentId: ptForm.ptEnrollmentId,
                trainingDate: ptForm.trainingDate,
                startedAt: ptForm.startedAt,
                endedAt: ptForm.endedAt,
              });
            }}
          >
            <div className="processing-modal-pt-form-head">
              <div>
                <strong>Ghi nhận buổi PT</strong>
                <span>{selectedItem.member.name} · {selectedItem.member.code}</span>
              </div>
              <button type="button" onClick={() => setSelectedItem(null)}>
                Đóng
              </button>
            </div>
            <div className="form-grid">
              <Field className="form-span" label="Gói PT" required>
                <Select
                  value={ptForm.ptEnrollmentId}
                  onChange={(event) => setPtForm({ ...ptForm, ptEnrollmentId: event.target.value })}
                >
                  {selectedOptions.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.type} · còn {row.remainingSessions}/{row.totalSessions} buổi
                    </option>
                  ))}
                </Select>
              </Field>
              {selectedPt ? (
                <div className="form-span processing-modal-pt-note">
                  {selectedPt.todaySlots?.length
                    ? `Lịch hôm nay: ${slotText(selectedPt.todaySlots)}`
                    : "Không có lịch PT hôm nay, nhưng hội viên còn đăng ký PT."}
                  {selectedPt.coaches?.length
                    ? ` · Coach: ${selectedPt.coaches.map((coach) => coach.name).join(", ")}`
                    : ""}
                </div>
              ) : null}
              <Field label="Ngày tập" required>
                <Input
                  type="date"
                  value={ptForm.trainingDate}
                  onChange={(event) => setPtForm({ ...ptForm, trainingDate: event.target.value })}
                />
              </Field>
              <Field label="Bắt đầu" required>
                <Input
                  type="datetime-local"
                  value={ptForm.startedAt}
                  onChange={(event) => setPtForm({ ...ptForm, startedAt: event.target.value })}
                />
              </Field>
              <Field label="Kết thúc" required>
                <Input
                  type="datetime-local"
                  value={ptForm.endedAt}
                  onChange={(event) => setPtForm({ ...ptForm, endedAt: event.target.value })}
                />
              </Field>
            </div>
            <div className="form-actions">
              <Button
                type="submit"
                loading={decision.isPending && decision.variables?.decision === "pt"}
                loadingText="Đang ghi..."
                disabled={
                  !ptForm.ptEnrollmentId ||
                  !ptForm.trainingDate ||
                  !ptForm.startedAt ||
                  !ptForm.endedAt
                }
              >
                <CheckCircle2 size={14} /> Xác nhận tập PT
              </Button>
            </div>
          </form>
        )}
      </div>
      <div className="form-actions">
        <Button variant="secondary" onClick={onClose}>
          Đóng
        </Button>
      </div>
    </Modal>
  );
}

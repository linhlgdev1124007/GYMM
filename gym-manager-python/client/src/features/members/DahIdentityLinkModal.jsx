import { useMutation, useQuery } from "@tanstack/react-query";
import { RefreshCw, ScanFace } from "lucide-react";
import { api } from "../../services/api";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { dateTime } from "../../utils/format";

export function DahIdentityLinkModal({
  open,
  onClose,
  memberId,
  memberName,
  onLinked,
  onSelect,
  targetType = "member",
  error,
}) {
  const candidates = useQuery({
    queryKey: ["dah-identity-candidates", targetType],
    queryFn: () => api(`/api/dah/identity-candidates?limit=12&targetType=${targetType}`),
    enabled: open,
    refetchInterval: open ? 4000 : false,
  });
  const assign = useMutation({
    mutationFn: (eventId) =>
      api(`/${targetType === "employee" ? "api/employees" : "api/members"}/${memberId}/dah-identity`, {
        method: "POST",
        body: { eventId },
      }),
    onSuccess: (result) => {
      onLinked?.(result);
      onClose();
    },
  });
  const selectCandidate = (row) => {
    if (memberId) {
      assign.mutate(row.eventId);
      return;
    }
    onSelect?.(row);
    onClose();
  };
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Liên kết định danh DAH"
      description={memberName || `Chọn PersonUUID chưa gán cho ${targetType === "employee" ? "nhân viên" : "hội viên"} nào`}
      size="lg"
    >
      <div className="modal-body">
        <div className="identity-link-toolbar">
          <div>
            <strong>Face mới quét gần đây</strong>
            <span>Danh sách tự cập nhật mỗi vài giây.</span>
          </div>
          <Button
            type="button"
            variant="secondary"
            onClick={() => candidates.refetch()}
            loading={candidates.isFetching}
            loadingText="Đang tải..."
          >
            <RefreshCw size={14} /> Làm mới
          </Button>
        </div>
        {(assign.error || candidates.error || error) && (
          <div className="inline-error mt-3">
            {assign.error?.message || candidates.error?.message || error}
          </div>
        )}
        {candidates.isLoading ? (
          <div className="identity-candidate-list mt-4">
            <div className="skeleton h-20" />
            <div className="skeleton h-20" />
            <div className="skeleton h-20" />
          </div>
        ) : candidates.data?.items?.length ? (
          <div className="identity-candidate-list mt-4">
            {candidates.data.items.map((row) => (
              <button
                key={row.eventId}
                type="button"
                className="identity-candidate"
                disabled={assign.isPending}
                onClick={() => selectCandidate(row)}
              >
                <div className="identity-face">
                  {row.imageData ? (
                    <img src={row.imageData} alt="" />
                  ) : (
                    <ScanFace size={22} />
                  )}
                </div>
                <div>
                  <strong>{row.name || "Khách vừa quét"}</strong>
                  <span>{row.personUuid}</span>
                  <small>
                    {row.device || "DAH"} · {dateTime(row.eventTime)}
                    {row.similarity ? ` · ${Number(row.similarity).toFixed(1)}%` : ""}
                  </small>
                </div>
              </button>
            ))}
          </div>
        ) : (
          <div className="empty-state compact mt-4">
            <ScanFace size={28} />
            <strong>Chưa có face mới chưa gán</strong>
            <p>Cho người cần liên kết quét mặt trên DAH rồi bấm làm mới.</p>
          </div>
        )}
      </div>
      <div className="form-actions">
        <Button data-modal-close variant="secondary" onClick={onClose}>
          Đóng
        </Button>
      </div>
    </Modal>
  );
}

import { useEffect, useState } from "react";
import { ExternalLink, ImagePlus } from "lucide-react";
import { Modal } from "../ui/Modal";
import { Button } from "../ui/Button";
import { ReceiptPicker } from "../ui/ReceiptPicker";
import { dateTime, money } from "../../utils/format";

const methods = {
  cash: "Tiền mặt",
  bank_transfer: "Chuyển khoản",
  card: "Thẻ",
};

export function PaymentReceiptModal({
  payment,
  open,
  onClose,
  onUpload,
  pending,
  error,
}) {
  const [files, setFiles] = useState([]);
  useEffect(() => setFiles([]), [payment?.id, open]);
  if (!payment) return null;
  const submit = (event) => {
    event.preventDefault();
    const data = new FormData();
    files.forEach((file) => data.append("receipts", file));
    onUpload(data);
  };
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Chứng từ · ${payment.number}`}
      description={`${money(payment.amount)} · ${methods[payment.method] || payment.method} · ${dateTime(payment.paidAt)}`}
      dirty={files.length > 0}
      size="lg"
    >
      <form onSubmit={submit}>
        <div className="modal-body space-y-5">
          <section>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="form-section-title !mb-0">Chứng từ đã lưu</h3>
              <span className="text-[11px] text-slate-400">
                {payment.receipts?.length || 0} ảnh
              </span>
            </div>
            {payment.receipts?.length ? (
              <div className="receipt-gallery">
                {payment.receipts.map((receipt, index) => (
                  <a
                    key={receipt.id || `${receipt.url}-${index}`}
                    href={receipt.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <img
                      src={receipt.url}
                      alt={receipt.name || `Chứng từ ${index + 1}`}
                    />
                    <span>
                      <strong>{receipt.name || `Chứng từ ${index + 1}`}</strong>
                      <small>{receipt.uploadedBy || "Dữ liệu trước đây"}</small>
                    </span>
                    <ExternalLink size={13} />
                  </a>
                ))}
              </div>
            ) : (
              <div className="receipt-empty">
                <ImagePlus size={20} />
                <span>Giao dịch này chưa có ảnh chứng từ.</span>
              </div>
            )}
          </section>
          <section className="form-section">
            <h3 className="form-section-title">Bổ sung chứng từ</h3>
            <ReceiptPicker
              files={files}
              onChange={setFiles}
              disabled={pending}
            />
          </section>
          {error && <div className="inline-error">{error}</div>}
        </div>
        <div className="form-actions">
          <Button data-modal-close variant="secondary" onClick={onClose}>
            Đóng
          </Button>
          <Button
            type="submit"
            loading={pending}
            loadingText="Đang tải lên…"
            disabled={!files.length}
          >
            Thêm {files.length || ""} ảnh
          </Button>
        </div>
      </form>
    </Modal>
  );
}

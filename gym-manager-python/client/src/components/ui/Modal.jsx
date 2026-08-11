import { AlertTriangle, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

const modalSizes = { sm: "max-w-sm", md: "max-w-lg", lg: "max-w-2xl" };

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  size = "md",
  dirty = false,
}) {
  const panel = useRef(null);
  const returnFocus = useRef(null);
  const dirtyRef = useRef(dirty);
  const closeRef = useRef(onClose);
  const discardFocus = useRef(null);
  const discardPanel = useRef(null);
  const confirmDiscardRef = useRef(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  dirtyRef.current = dirty;
  closeRef.current = onClose;
  const titleId = useId();
  const descriptionId = useId();
  confirmDiscardRef.current = confirmDiscard;
  useEffect(() => {
    if (!open) setConfirmDiscard(false);
  }, [open]);
  const requestClose = (force = false) => {
    if (dirtyRef.current && !force) {
      setConfirmDiscard(true);
      requestAnimationFrame(() => discardFocus.current?.focus());
      return;
    }
    setConfirmDiscard(false);
    closeRef.current();
  };
  useEffect(() => {
    if (!open) return undefined;
    returnFocus.current = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const keydown = (event) => {
      if (event.key === "Escape") {
        if (confirmDiscardRef.current) setConfirmDiscard(false);
        else requestClose();
      }
      if (event.key !== "Tab") return;
      const focusRoot = confirmDiscardRef.current ? discardPanel.current : panel.current;
      const focusable = [
        ...(focusRoot?.querySelectorAll(
          'button:not([disabled]), input:not([disabled]):not([tabindex="-1"]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
        ) || []),
      ];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      }
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", keydown);
    requestAnimationFrame(() => {
      const target =
        panel.current?.querySelector("[autofocus]") ||
        panel.current?.querySelector(
          "input:not([type='hidden']):not([tabindex='-1']), select, textarea",
        ) ||
        panel.current?.querySelector("button");
      target?.focus();
    });
    return () => {
      document.removeEventListener("keydown", keydown);
      document.body.style.overflow = previousOverflow;
      returnFocus.current?.focus?.();
    };
  }, [open]);
  if (!open) return null;
  return (
    <div
      className="modal-layer"
      role="presentation"
      onMouseDown={(event) =>
        event.target === event.currentTarget && requestClose()
      }
    >
      <section
        ref={panel}
        className={`modal ${modalSizes[size] || modalSizes.md}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        onClickCapture={(event) => {
          if (event.target.closest("[data-modal-close]")) {
            event.preventDefault();
            event.stopPropagation();
            requestClose();
          }
        }}
      >
        <header className="modal-header">
          <div>
            <h2 id={titleId}>{title}</h2>
            {description && <p id={descriptionId}>{description}</p>}
          </div>
          <button
            type="button"
            className="icon-button"
            onClick={() => requestClose()}
            aria-label="Đóng"
          >
            <X size={17} />
          </button>
        </header>
        {children}
        {confirmDiscard && (
          <div className="discard-confirm" role="alertdialog" aria-modal="true" aria-label="Bỏ thay đổi chưa lưu">
            <div ref={discardPanel} className="discard-confirm-card">
              <div className="discard-confirm-icon"><AlertTriangle size={18} /></div>
              <div>
                <h3>Bỏ các thay đổi chưa lưu?</h3>
                <p>Dữ liệu bạn vừa nhập trong biểu mẫu này sẽ không được lưu lại.</p>
              </div>
              <div className="discard-confirm-actions">
                <button ref={discardFocus} type="button" className="btn btn-secondary" onClick={() => setConfirmDiscard(false)}>
                  Tiếp tục chỉnh sửa
                </button>
                <button type="button" className="btn btn-danger" onClick={() => requestClose(true)}>
                  Bỏ thay đổi
                </button>
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

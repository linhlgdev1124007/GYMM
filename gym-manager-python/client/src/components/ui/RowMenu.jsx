import { ChevronDown, MoreHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export function RowMenu({ children, label = "", className = "" }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const buttonRef = useRef(null);
  const menuRef = useRef(null);

  const toggle = (event) => {
    event.stopPropagation();
    const rect = event.currentTarget.getBoundingClientRect();
    const width = 176;
    setPosition({
      top: rect.bottom + 4,
      left: Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8)),
    });
    setOpen((current) => !current);
  };

  useEffect(() => {
    if (!open) return undefined;
    const close = (event) => {
      if (
        buttonRef.current?.contains(event.target) ||
        menuRef.current?.contains(event.target)
      ) {
        return;
      }
      setOpen(false);
    };
    const closeOnLayoutChange = () => setOpen(false);
    document.addEventListener("pointerdown", close);
    window.addEventListener("resize", closeOnLayoutChange);
    window.addEventListener("scroll", closeOnLayoutChange, true);
    return () => {
      document.removeEventListener("pointerdown", close);
      window.removeEventListener("resize", closeOnLayoutChange);
      window.removeEventListener("scroll", closeOnLayoutChange, true);
    };
  }, [open]);

  return (
    <span className={`row-menu ${label ? "row-menu-labeled" : ""} ${className}`} onClick={(event) => event.stopPropagation()}>
      <button
        ref={buttonRef}
        type="button"
        aria-label={label || "Mở menu thao tác"}
        aria-expanded={open}
        onClick={toggle}
      >
        {label ? <><span>{label}</span><ChevronDown size={14} /></> : <MoreHorizontal size={18} />}
      </button>
      {open &&
        createPortal(
          <div
            ref={menuRef}
            className="row-menu-popover"
            style={position}
            onClick={(event) => {
              event.stopPropagation();
              setOpen(false);
            }}
          >
            {children}
          </div>,
          document.body,
        )}
    </span>
  );
}

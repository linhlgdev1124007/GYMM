import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Search } from "lucide-react";

export function SearchableSelect({
  value,
  onChange,
  options = [],
  placeholder = "Chọn…",
  searchPlaceholder = "Tìm kiếm…",
  ariaLabel,
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const root = useRef(null);
  useEffect(() => {
    const close = (event) => {
      if (!root.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, []);
  const selected = options.find((item) => String(item.value) === String(value));
  const filtered = useMemo(() => {
    const term = query.toLocaleLowerCase("vi");
    return options
      .filter((item) =>
        `${item.label} ${item.meta || ""}`
          .toLocaleLowerCase("vi")
          .includes(term),
      )
      .slice(0, 50);
  }, [options, query]);
  return (
    <div className="combobox" ref={root}>
      <button
        type="button"
        className="input combobox-trigger"
        onClick={() => setOpen(!open)}
        aria-label={ariaLabel}
        aria-expanded={open}
      >
        <span className={selected ? "" : "text-slate-400"}>
          {selected?.label || placeholder}
        </span>
        <ChevronDown size={14} />
      </button>
      {open && (
        <div className="combobox-popover">
          <div className="combobox-search">
            <Search size={14} />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={searchPlaceholder}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  e.stopPropagation();
                  setOpen(false);
                }
              }}
            />
          </div>
          <div className="combobox-options">
            {filtered.map((item) => (
              <button
                type="button"
                key={item.value}
                onClick={() => {
                  onChange(String(item.value));
                  setOpen(false);
                  setQuery("");
                }}
              >
                <span>
                  <strong>{item.label}</strong>
                  {item.meta && <small>{item.meta}</small>}
                </span>
                {String(item.value) === String(value) && <Check size={14} />}
              </button>
            ))}
            {!filtered.length && <p>Không tìm thấy kết quả.</p>}
          </div>
        </div>
      )}
    </div>
  );
}

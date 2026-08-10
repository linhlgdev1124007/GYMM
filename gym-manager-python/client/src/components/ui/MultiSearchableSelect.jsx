import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Search, X } from "lucide-react";

export function MultiSearchableSelect({
  values = [],
  onChange,
  options = [],
  placeholder = "Chưa phân công Coach",
  searchPlaceholder = "Tìm Coach…",
  ariaLabel,
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const root = useRef(null);
  const selectedValues = values.map(String);
  useEffect(() => {
    const close = (event) => {
      if (!root.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, []);
  const selected = options.filter((item) =>
    selectedValues.includes(String(item.value)),
  );
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
  useEffect(() => setActive(0), [query, open]);
  const toggle = (value) => {
    const normalized = String(value);
    onChange(
      selectedValues.includes(normalized)
        ? selectedValues.filter((item) => item !== normalized)
        : [...selectedValues, normalized],
    );
  };
  return (
    <div className="combobox" ref={root}>
      <div className="flex min-h-10 flex-wrap items-center gap-1.5 rounded-md border border-slate-200 bg-white p-1.5">
        {selected.map((item) => (
          <span
            key={item.value}
            className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700"
          >
            {item.label}
            <button
              type="button"
              className="text-slate-400 hover:text-slate-800"
              onClick={() => toggle(item.value)}
              aria-label={`Bỏ ${item.label}`}
            >
              <X size={12} />
            </button>
          </span>
        ))}
        <button
          type="button"
          className="flex min-w-36 flex-1 items-center justify-between gap-2 px-1.5 py-1 text-left text-xs"
          onClick={() => setOpen(!open)}
          aria-label={ariaLabel}
          aria-expanded={open}
        >
          <span
            className={selected.length ? "text-slate-500" : "text-slate-400"}
          >
            {selected.length ? "+ Thêm Coach" : placeholder}
          </span>
          <ChevronDown size={14} className="shrink-0 text-slate-400" />
        </button>
      </div>
      {open && (
        <div className="combobox-popover">
          <div className="combobox-search">
            <Search size={14} />
            <input
              autoFocus
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={searchPlaceholder}
              onKeyDown={(event) => {
                if (event.key === "Escape") setOpen(false);
                if (event.key === "ArrowDown") {
                  event.preventDefault();
                  setActive((value) =>
                    Math.min(value + 1, filtered.length - 1),
                  );
                }
                if (event.key === "ArrowUp") {
                  event.preventDefault();
                  setActive((value) => Math.max(value - 1, 0));
                }
                if (event.key === "Enter" && filtered[active]) {
                  event.preventDefault();
                  toggle(filtered[active].value);
                }
              }}
            />
          </div>
          <div className="combobox-options">
            {filtered.map((item, index) => {
              const checked = selectedValues.includes(String(item.value));
              return (
                <button
                  type="button"
                  key={item.value}
                  className={index === active ? "bg-slate-50" : ""}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => toggle(item.value)}
                >
                  <span>
                    <strong>{item.label}</strong>
                    {item.meta && <small>{item.meta}</small>}
                  </span>
                  {checked && <Check size={14} />}
                </button>
              );
            })}
            {!filtered.length && <p>Không tìm thấy Coach.</p>}
          </div>
        </div>
      )}
    </div>
  );
}

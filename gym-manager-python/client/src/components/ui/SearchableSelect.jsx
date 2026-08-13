import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Search } from "lucide-react";

export function SearchableSelect({
  value,
  onChange,
  options = [],
  placeholder = "Chọn…",
  searchPlaceholder = "Tìm kiếm…",
  ariaLabel,
  clearable = false,
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
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
        `${item.label} ${item.meta || ""} ${item.group || ""}`
          .toLocaleLowerCase("vi")
          .includes(term),
      )
      .slice(0, 50);
  }, [options, query]);
  const rendered = useMemo(() => {
    const rows = [];
    let currentGroup = null;
    filtered.forEach((item, index) => {
      const group = item.group || "";
      if (group && group !== currentGroup) {
        rows.push({ type: "group", key: `group-${group}`, label: group });
        currentGroup = group;
      }
      rows.push({ type: "option", item, index });
    });
    return rows;
  }, [filtered]);
  useEffect(() => setActive(0), [query, open]);
  return (
    <div className="combobox" ref={root}>
      <button
        type="button"
        className="input combobox-trigger"
        onClick={() => setOpen(!open)}
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-haspopup="listbox"
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
                if (e.nativeEvent?.isComposing || e.isComposing) return;
                if (e.key === "Escape") {
                  e.stopPropagation();
                  setOpen(false);
                }
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setActive((value) =>
                    Math.min(value + 1, filtered.length - 1),
                  );
                }
                if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setActive((value) => Math.max(value - 1, 0));
                }
                if (e.key === "Enter" && filtered[active]) {
                  e.preventDefault();
                  onChange(String(filtered[active].value));
                  setOpen(false);
                  setQuery("");
                }
              }}
            />
          </div>
          <div className="combobox-options" role="listbox">
            {clearable && value && (
              <button
                type="button"
                className="text-slate-500"
                onClick={() => {
                  onChange("");
                  setOpen(false);
                  setQuery("");
                }}
              >
                Không chọn
              </button>
            )}
            {rendered.map((row) =>
              row.type === "group" ? (
                <div className="combobox-group" key={row.key}>
                  {row.label}
                </div>
              ) : (
                <button
                  type="button"
                  key={row.item.value}
                  role="option"
                  aria-selected={String(row.item.value) === String(value)}
                  className={row.index === active ? "bg-slate-50" : ""}
                  onMouseEnter={() => setActive(row.index)}
                  onClick={() => {
                    onChange(String(row.item.value));
                    setOpen(false);
                    setQuery("");
                  }}
                >
                  <span>
                    <strong>{row.item.label}</strong>
                    {row.item.meta && <small>{row.item.meta}</small>}
                  </span>
                  {String(row.item.value) === String(value) && <Check size={14} />}
                </button>
              ),
            )}
            {!filtered.length && <p>Không tìm thấy kết quả.</p>}
          </div>
        </div>
      )}
    </div>
  );
}

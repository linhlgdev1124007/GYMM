import { LoaderCircle } from "lucide-react";

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  type = "button",
  loading = false,
  loadingText,
  children,
  disabled,
  ...props
}) {
  return (
    <button
      type={type}
      className={`btn btn-${variant} btn-${size} ${className}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading && <LoaderCircle className="animate-spin" size={15} />}
      {loading ? loadingText || children : children}
    </button>
  );
}

export function Field({ label, required, hint, error, children, className = '' }) {
  return <label className={`field ${className}`}><span className="field-label">{label}{required && <span aria-hidden="true"> *</span>}</span>{children}{error && <span className="field-error">{error}</span>}{hint && !error && <span className="field-hint">{hint}</span>}</label>
}
export const Input = (props) => <input className="input" {...props} />
export const Select = (props) => <select className="input" {...props} />
export const Textarea = (props) => <textarea className="input min-h-24 resize-y" {...props} />

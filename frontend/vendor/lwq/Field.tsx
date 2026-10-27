import { useId } from 'react'
import type { InputHTMLAttributes, SelectHTMLAttributes } from 'react'
import { Search, X } from 'lucide-react'
import { Button } from './Button.tsx'

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  label: string
  hint?: string
  error?: string
  success?: string
}

export function TextField({ label, hint, error, success, className = '', ...props }: TextFieldProps) {
  const id = useId()
  const messageId = `${id}-message`
  const message = error ?? success ?? hint
  const tone = error ? 'error' : success ? 'success' : 'hint'
  return (
    <div className="ds-field">
      <label className="ds-field-label" htmlFor={id}>{label}</label>
      <input
        {...props}
        id={id}
        className={`ds-input ${className}`.trim()}
        aria-invalid={error ? true : false}
        aria-describedby={message ? messageId : undefined}
      />
      {message && <span id={messageId} className={`ds-field-message ds-field-${tone}`}>{message}</span>}
    </div>
  )
}

interface SearchFieldProps {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  clearLabel?: string
}

export function SearchField({ label, value, onChange, placeholder, clearLabel = '清空搜索' }: SearchFieldProps) {
  const id = useId()
  return (
    <div className="dp-search ds-search" role="search" aria-label={label}>
      <Search size={17} aria-hidden="true" />
      <input id={id} type="search" aria-label={label} placeholder={placeholder} value={value} onChange={event => onChange(event.target.value)} />
      {value && (
        <Button variant="ghost" size="icon-xs" className="ds-search-clear" aria-label={clearLabel} onClick={() => onChange('')}>
          <X size={15} aria-hidden="true" />
        </Button>
      )}
    </div>
  )
}

interface SelectOption {
  value: string
  label: string
}

interface SelectFieldProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'children' | 'onChange' | 'value'> {
  label: string
  description?: string
  options: SelectOption[]
  value: string
  onChange: (value: string) => void
}

export function SelectField({ label, description, options, value, onChange, className = '', ...props }: SelectFieldProps) {
  const id = useId()
  return (
    <div className="dp-field-row ds-select-field">
      <div>
        <label htmlFor={id}>{label}</label>
        {description && <p>{description}</p>}
      </div>
      <select {...props} id={id} className={`ds-select ${className}`.trim()} value={value} onChange={event => onChange(event.target.value)}>
        {options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </div>
  )
}

import type { ReactNode } from 'react'
import { AlertCircle, CircleCheck, Info, X } from 'lucide-react'
import { Button } from './Button.tsx'

type FeedbackTone = 'success' | 'error' | 'info'

interface InlineFeedbackProps {
  tone?: FeedbackTone
  presentation?: 'inline' | 'plain'
  children: ReactNode
  action?: ReactNode
  onDismiss?: () => void
  dismissLabel?: string
}

const ICONS = { success: CircleCheck, error: AlertCircle, info: Info }

export function InlineFeedback({
  tone = 'info',
  presentation = 'inline',
  children,
  action,
  onDismiss,
  dismissLabel = '关闭提示',
}: InlineFeedbackProps) {
  const Icon = ICONS[tone]
  return (
    <div
      className={presentation === 'inline'
        ? `dp-inline-feedback ds-feedback ds-feedback-${tone}`
        : `ds-feedback-plain ds-feedback-${tone}`}
      role="status"
    >
      <Icon size={17} aria-hidden="true" />
      <p>{children}</p>
      {action}
      {onDismiss && (
        <Button variant="ghost" size="icon-xs" className="ds-feedback-dismiss" aria-label={dismissLabel} onClick={onDismiss}>
          <X size={15} aria-hidden="true" />
        </Button>
      )}
    </div>
  )
}

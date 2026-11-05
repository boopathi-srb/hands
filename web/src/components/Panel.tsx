import type { ReactNode } from 'react'

interface PanelProps {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  flush?: boolean
  className?: string
  id?: string
}

export function Panel({ title, subtitle, actions, children, flush, className, id }: PanelProps) {
  const headingId = id ? `${id}-title` : undefined
  return (
    <section className={`panel ${className ?? ''}`} aria-labelledby={headingId} id={id}>
      {title || actions ? (
        <header className="panel-head">
          <div className="stack-sm" style={{ gap: 0 }}>
            {title ? <h2 id={headingId}>{title}</h2> : null}
            {subtitle ? <span className="panel-sub">{subtitle}</span> : null}
          </div>
          {actions ? <div className="row">{actions}</div> : null}
        </header>
      ) : null}
      <div className={`panel-body ${flush ? 'flush' : ''}`}>{children}</div>
    </section>
  )
}

interface PageHeaderProps {
  eyebrow?: ReactNode
  title: ReactNode
  badges?: ReactNode
  lede?: ReactNode
  actions?: ReactNode
}

export function PageHeader({ eyebrow, title, badges, lede, actions }: PageHeaderProps) {
  return (
    <header className="page-head">
      <div className="page-head-text">
        {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
        <div className="title-row">
          <h1>{title}</h1>
          {badges}
        </div>
        {lede ? <p className="page-lede">{lede}</p> : null}
      </div>
      {actions ? <div className="row">{actions}</div> : null}
    </header>
  )
}

export interface KeyValueItem {
  label: string
  value: ReactNode
}

/** Definition list; items whose value is null, undefined or '' are skipped. */
export function KeyValueList({ items, label }: { items: KeyValueItem[]; label?: string }) {
  const visible = items.filter((item) => item.value !== null && item.value !== undefined && item.value !== '')
  return (
    <dl className="kv" aria-label={label}>
      {visible.map((item) => (
        <div key={item.label} style={{ display: 'contents' }}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
    </div>
  )
}

export type StatusType = 'green' | 'yellow' | 'red' | null

export type SizeType = 'small' | 'medium' | 'large' | 'full'

export interface CardProps {
  label: string
  value: any
  status: StatusType
  size: SizeType
}

// maps status → existing CSS variable from index.css
export function statusToColor(status: StatusType): string {
  if (status === 'green')  return 'var(--success)'
  if (status === 'yellow') return 'var(--warning)'
  if (status === 'red')    return 'var(--danger)'
  return 'var(--text-dim)'
}

// maps size → CSS grid-column span value
export function sizeToGridSpan(size: SizeType): string {
  if (size === 'full')   return '1 / -1'
  if (size === 'large')  return 'span 2'
  if (size === 'medium') return 'span 1'
  return 'span 1'   // small
}

import { useRef } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'

/**
 * A tablist with the full WAI-ARIA keyboard contract.
 *
 * ## Why the model is generic
 *
 * The page owns the tab keys and their labels; this component owns the
 * behaviour. That keeps the six-tab list testable as data (`settings/tabs.ts`)
 * while the keyboard logic stays in one place.
 *
 * ## The keyboard contract
 *
 * - `ArrowRight` / `ArrowLeft` move by one, `ArrowUp` / `ArrowDown` too
 *   (the control is vertical on a wide screen and horizontal below it, and a
 *   user should not have to know which).
 * - In RTL the horizontal arrows are reversed: `ArrowRight` means "the tab to
 *   the right", which is the previous one in DOM order.
 * - `Home` / `End` jump to the first and last tab.
 * - Only the selected tab is in the page's tab order (roving tabindex).
 *
 * The panel ids are derived from `idBase`, so the page only has to render
 * `id={panelId(key)}` and `aria-labelledby={tabId(key)}` on its panel.
 */
export interface TabItem<K extends string> {
  key: K
  label: string
  icon?: ReactNode
}

export function tabId(idBase: string, key: string): string {
  return `${idBase}-tab-${key}`
}

export function panelId(idBase: string, key: string): string {
  return `${idBase}-panel-${key}`
}

interface TabsProps<K extends string> {
  idBase: string
  items: readonly TabItem<K>[]
  active: K
  onChange: (key: K) => void
  label: string
}

export function Tabs<K extends string>({ idBase, items, active, onChange, label }: TabsProps<K>) {
  const list = useRef<HTMLDivElement>(null)

  const focusTab = (key: K) => {
    const element = list.current?.querySelector<HTMLButtonElement>(`#${CSS.escape(tabId(idBase, key))}`)
    element?.focus()
  }

  const select = (key: K | undefined) => {
    if (!key) return
    onChange(key)
    focusTab(key)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = items.findIndex((item) => item.key === active)
    if (index < 0) return
    const rtl = getComputedStyle(event.currentTarget).direction === 'rtl'
    switch (event.key) {
      case 'ArrowRight':
        event.preventDefault()
        select(items[(index + (rtl ? -1 : 1) + items.length) % items.length]?.key)
        break
      case 'ArrowLeft':
        event.preventDefault()
        select(items[(index + (rtl ? 1 : -1) + items.length) % items.length]?.key)
        break
      case 'ArrowDown':
        event.preventDefault()
        select(items[(index + 1) % items.length]?.key)
        break
      case 'ArrowUp':
        event.preventDefault()
        select(items[(index - 1 + items.length) % items.length]?.key)
        break
      case 'Home':
        event.preventDefault()
        select(items[0]?.key)
        break
      case 'End':
        event.preventDefault()
        select(items[items.length - 1]?.key)
        break
      default:
        break
    }
  }

  return (
    <div
      ref={list}
      role="tablist"
      aria-label={label}
      aria-orientation="vertical"
      className="ui-tabs"
      onKeyDown={onKeyDown}
    >
      {items.map((item) => {
        const selected = item.key === active
        return (
          <button
            key={item.key}
            id={tabId(idBase, item.key)}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={panelId(idBase, item.key)}
            tabIndex={selected ? 0 : -1}
            className="ui-tab"
            onClick={() => onChange(item.key)}
          >
            {item.icon}
            {item.label}
          </button>
        )
      })}
    </div>
  )
}
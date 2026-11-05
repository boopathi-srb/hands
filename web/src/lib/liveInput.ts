/**
 * Operator live-view input: maps browser pointer and keyboard events to the console websocket
 * protocol (hands/console/live.py). Coordinates are sent in frame pixels, because the canvas is
 * scaled with CSS and the frame is the session's real viewport.
 */

export interface Point {
  x: number
  y: number
}

export interface ElementBox {
  left: number
  top: number
  width: number
  height: number
}

export interface FrameSize {
  width: number
  height: number
}

/**
 * Converts a click at client coordinates on a CSS-scaled canvas to frame pixels, clamped to the
 * frame. Returns null when the canvas has no size yet (not laid out) or no frame has arrived.
 */
export function scaleClickToFrame(clientX: number, clientY: number, box: ElementBox, frame: FrameSize): Point | null {
  if (box.width <= 0 || box.height <= 0 || frame.width <= 0 || frame.height <= 0) return null
  const x = ((clientX - box.left) * frame.width) / box.width
  const y = ((clientY - box.top) * frame.height) / box.height
  return {
    x: Math.round(clamp(x, 0, frame.width - 1)),
    y: Math.round(clamp(y, 0, frame.height - 1)),
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export interface KeyLike {
  key: string
  ctrlKey: boolean
  metaKey: boolean
  altKey: boolean
}

export type KeyMessage =
  | { kind: 'key'; event: { type: 'char'; key: string; text: string } }
  | { kind: 'key'; event: { type: 'down' | 'up'; key: string } }

export interface PointerMessage {
  kind: 'pointer'
  event: { type: 'click'; x: number; y: number; button: 'left' }
}

/** Keys the browser reports while the canvas has focus that must never reach the session alone. */
const IGNORED_KEYS = ['Shift', 'Control', 'Alt', 'Meta', 'CapsLock', 'Dead', 'Unidentified', 'Process']

export function isPrintableKey(event: KeyLike): boolean {
  return event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey
}

/**
 * keydown: printable keys become one `char` (text typed), named keys (Enter, Backspace, Tab,
 * arrows...) become `down`. keyup: only named keys send `up`, since `char` is already complete.
 * Bare modifier presses return null.
 */
export function keyEventToMessage(event: KeyLike, phase: 'down' | 'up'): KeyMessage | null {
  if (!event.key || IGNORED_KEYS.includes(event.key)) return null
  if (isPrintableKey(event)) {
    return phase === 'down' ? { kind: 'key', event: { type: 'char', key: event.key, text: event.key } } : null
  }
  return { kind: 'key', event: { type: phase, key: event.key } }
}

export function clickMessage(point: Point): PointerMessage {
  return { kind: 'pointer', event: { type: 'click', x: point.x, y: point.y, button: 'left' } }
}

// ---------------------------------------------------------------- server messages

export interface HumanActionView {
  kind: string
  /** Consecutive presses of the same key in the same field, collapsed into one entry. */
  count?: number
  text_length?: number | null
  key?: string | null
  node_role?: string | null
  node_name?: string | null
}

export type ServerMessage =
  | { type: 'connected'; session_id: string; operator_id: string; lease: unknown }
  | { type: 'frame'; mime: string; data: string }
  | { type: 'input_accepted'; action: HumanActionView | null }
  | { type: 'input_rejected'; code: string; message: string }
  | { type: 'control_lost'; lease: unknown }
  | { type: 'error'; code: string; message: string }

const SERVER_TYPES = ['connected', 'frame', 'input_accepted', 'input_rejected', 'control_lost', 'error']

/** Parses one websocket message; unknown or malformed payloads return null (and are logged). */
export function parseServerMessage(raw: string): ServerMessage | null {
  let parsed: unknown
  // Untrusted network input: JSON.parse is the one place that can throw here.
  try {
    parsed = JSON.parse(raw)
  } catch (error) {
    console.error('parseServerMessage: invalid JSON from live view', { length: raw.length, error })
    return null
  }
  const type = (parsed as { type?: unknown } | null)?.type
  if (typeof type !== 'string' || !SERVER_TYPES.includes(type)) {
    console.warn('parseServerMessage: unknown message type', type)
    return null
  }
  return parsed as ServerMessage
}

/** "click textbox “Security Answer”", "type 19 chars into textbox", "press Enter". */
export function describeHumanAction(action: HumanActionView): string {
  const target = action.node_role ? ` ${action.node_role}${action.node_name ? ` “${action.node_name}”` : ''}` : ''
  if (action.kind === 'type') {
    const count = action.text_length ?? 0
    return `type ${count} char${count === 1 ? '' : 's'}${target ? ` into${target}` : ''}`
  }
  if (action.kind === 'press') {
    const times = action.count && action.count > 1 ? ` ×${action.count}` : ''
    return `press ${action.key ?? 'key'}${times}${target ? ` in${target}` : ''}`
  }
  return `${action.kind}${target}`
}

function sameField(left: HumanActionView, right: HumanActionView): boolean {
  return left.node_role === right.node_role && left.node_name === right.node_name
}

/**
 * Consecutive typing into the same field collapses into one entry (as the evidence shows it), and
 * repeated presses of the same key into one entry with a count.
 */
export function appendHumanAction(actions: HumanActionView[], next: HumanActionView): HumanActionView[] {
  const previous = actions[actions.length - 1]
  if (!previous || !sameField(previous, next) || previous.kind !== next.kind) return [...actions, { ...next }]
  if (next.kind === 'type') {
    const merged = { ...previous, text_length: (previous.text_length ?? 0) + (next.text_length ?? 0) }
    return [...actions.slice(0, -1), merged]
  }
  if (next.kind === 'press' && previous.key === next.key) {
    const merged = { ...previous, count: (previous.count ?? 1) + (next.count ?? 1) }
    return [...actions.slice(0, -1), merged]
  }
  return [...actions, { ...next }]
}

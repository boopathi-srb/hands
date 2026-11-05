import { describe, expect, it, vi } from 'vitest'
import {
  appendHumanAction,
  clickMessage,
  describeHumanAction,
  isPrintableKey,
  keyEventToMessage,
  parseServerMessage,
  scaleClickToFrame,
} from './liveInput'

const noModifiers = { ctrlKey: false, metaKey: false, altKey: false }

describe('scaleClickToFrame', () => {
  const frame = { width: 1280, height: 800 }

  it('maps a click on a half-size canvas to frame pixels', () => {
    const box = { left: 100, top: 50, width: 640, height: 400 }
    expect(scaleClickToFrame(100 + 320, 50 + 200, box, frame)).toEqual({ x: 640, y: 400 })
  })

  it('is identity when the canvas is shown at native size', () => {
    expect(scaleClickToFrame(479, 220, { left: 0, top: 0, width: 1280, height: 800 }, frame)).toEqual({ x: 479, y: 220 })
  })

  it('handles non-uniform scaling and rounds to whole pixels', () => {
    expect(scaleClickToFrame(10, 10, { left: 0, top: 0, width: 300, height: 100 }, { width: 1000, height: 500 })).toEqual({ x: 33, y: 50 })
  })

  it('clamps clicks on the border to the frame', () => {
    const box = { left: 0, top: 0, width: 640, height: 400 }
    expect(scaleClickToFrame(-5, 999, box, frame)).toEqual({ x: 0, y: 799 })
    expect(scaleClickToFrame(640, 400, box, frame)).toEqual({ x: 1279, y: 799 })
  })

  it('returns null before layout or before a frame exists', () => {
    expect(scaleClickToFrame(1, 1, { left: 0, top: 0, width: 0, height: 0 }, frame)).toBeNull()
    expect(scaleClickToFrame(1, 1, { left: 0, top: 0, width: 10, height: 10 }, { width: 0, height: 0 })).toBeNull()
  })
})

describe('isPrintableKey', () => {
  it('treats single characters without modifiers as printable', () => {
    expect(isPrintableKey({ key: 'a', ...noModifiers })).toBe(true)
    expect(isPrintableKey({ key: ' ', ...noModifiers })).toBe(true)
  })
  it('treats named keys and shortcuts as not printable', () => {
    expect(isPrintableKey({ key: 'Enter', ...noModifiers })).toBe(false)
    expect(isPrintableKey({ key: 'a', ...noModifiers, metaKey: true })).toBe(false)
  })
})

describe('keyEventToMessage', () => {
  it('sends printable keys as char on keydown only', () => {
    expect(keyEventToMessage({ key: 's', ...noModifiers }, 'down')).toEqual({ kind: 'key', event: { type: 'char', key: 's', text: 's' } })
    expect(keyEventToMessage({ key: 's', ...noModifiers }, 'up')).toBeNull()
  })
  it('sends named keys as down and up', () => {
    for (const key of ['Enter', 'Backspace', 'Tab', 'ArrowLeft']) {
      expect(keyEventToMessage({ key, ...noModifiers }, 'down')).toEqual({ kind: 'key', event: { type: 'down', key } })
      expect(keyEventToMessage({ key, ...noModifiers }, 'up')).toEqual({ kind: 'key', event: { type: 'up', key } })
    }
  })
  it('ignores bare modifiers and empty keys', () => {
    expect(keyEventToMessage({ key: 'Shift', ...noModifiers }, 'down')).toBeNull()
    expect(keyEventToMessage({ key: '', ...noModifiers }, 'down')).toBeNull()
  })
})

describe('clickMessage', () => {
  it('wraps a point in the pointer protocol', () => {
    expect(clickMessage({ x: 1, y: 2 })).toEqual({ kind: 'pointer', event: { type: 'click', x: 1, y: 2, button: 'left' } })
  })
})

describe('parseServerMessage', () => {
  it('parses known message types', () => {
    expect(parseServerMessage('{"type":"frame","mime":"image/png","data":"AAA"}')).toEqual({ type: 'frame', mime: 'image/png', data: 'AAA' })
    expect(parseServerMessage('{"type":"control_lost","lease":null}')?.type).toBe('control_lost')
  })
  it('returns null for invalid JSON, unknown types and non-objects', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    expect(parseServerMessage('not json')).toBeNull()
    expect(parseServerMessage('{"type":"surprise"}')).toBeNull()
    expect(parseServerMessage('null')).toBeNull()
    expect(parseServerMessage('')).toBeNull()
    error.mockRestore()
    warn.mockRestore()
  })
})

describe('describeHumanAction', () => {
  it('describes clicks, typing and key presses in artifact vocabulary', () => {
    expect(describeHumanAction({ kind: 'click', node_role: 'button', node_name: 'Verify' })).toBe('click button “Verify”')
    expect(describeHumanAction({ kind: 'type', text_length: 19, node_role: 'textbox', node_name: '' })).toBe('type 19 chars into textbox')
    expect(describeHumanAction({ kind: 'type', text_length: 1 })).toBe('type 1 char')
    expect(describeHumanAction({ kind: 'press', key: 'Enter' })).toBe('press Enter')
  })
  it('handles missing fields', () => {
    expect(describeHumanAction({ kind: 'scroll' })).toBe('scroll')
    expect(describeHumanAction({ kind: 'type' })).toBe('type 0 chars')
    expect(describeHumanAction({ kind: 'press', node_role: 'textbox' })).toBe('press key in textbox')
  })
})

describe('appendHumanAction', () => {
  it('merges consecutive typing into the same field', () => {
    const typed = { kind: 'type', text_length: 1, node_role: 'textbox', node_name: 'Answer' }
    const merged = appendHumanAction(appendHumanAction([], typed), typed)
    expect(merged).toEqual([{ ...typed, text_length: 2 }])
  })
  it('keeps typing into different fields and other actions separate', () => {
    const first = appendHumanAction([], { kind: 'type', text_length: 3, node_role: 'textbox', node_name: 'A' })
    const second = appendHumanAction(first, { kind: 'type', text_length: 2, node_role: 'textbox', node_name: 'B' })
    const third = appendHumanAction(second, { kind: 'click', node_role: 'button', node_name: 'Verify' })
    expect(third).toHaveLength(3)
  })
  it('collapses repeated presses of the same key with a count', () => {
    const backspace = { kind: 'press', key: 'Backspace', node_role: 'textbox', node_name: '' }
    const list = [backspace, backspace, backspace].reduce(appendHumanAction, [] as ReturnType<typeof appendHumanAction>)
    expect(list).toEqual([{ ...backspace, count: 3 }])
    expect(describeHumanAction(list[0])).toBe('press Backspace ×3 in textbox')
    expect(appendHumanAction(list, { ...backspace, key: 'Enter' })).toHaveLength(2)
  })
  it('does not merge clicks', () => {
    const click = { kind: 'click', node_role: 'button', node_name: 'Verify' }
    expect(appendHumanAction([click], click)).toHaveLength(2)
  })
  it('does not mutate the input list', () => {
    const list = [{ kind: 'type', text_length: 1 }]
    appendHumanAction(list, { kind: 'type', text_length: 1 })
    expect(list[0].text_length).toBe(1)
  })
})

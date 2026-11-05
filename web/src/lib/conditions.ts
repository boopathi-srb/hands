/**
 * Turns the declarative condition language (text visible, node present, location matches, dialog
 * open, value matches, all/any/not) into a readable tree. Components render the tree; they never
 * inspect raw condition JSON.
 */

import type { Condition } from '../api/types'

export interface Segment {
  text: string
  /** `literal` for product text and patterns, shown in mono; `plain` for connective words. */
  style: 'plain' | 'literal'
}

export interface ConditionNode {
  segments: Segment[]
  children: ConditionNode[]
}

const plain = (text: string): Segment => ({ text, style: 'plain' })
const literal = (text: string): Segment => ({ text, style: 'literal' })

function leaf(...segments: Segment[]): ConditionNode {
  return { segments, children: [] }
}

function textMatchQualifiers(regex?: boolean, caseSensitive?: boolean): Segment[] {
  const qualifiers = [regex ? 'regex' : null, caseSensitive ? 'case-sensitive' : null].filter(Boolean)
  return qualifiers.length ? [plain(` (${qualifiers.join(', ')})`)] : []
}

function describeLocation(pattern?: string | null, titlePattern?: string | null): ConditionNode {
  if (pattern && titlePattern) {
    return leaf(plain('Location matches '), literal(pattern), plain(' and title matches '), literal(titlePattern))
  }
  if (pattern) return leaf(plain('Location matches '), literal(pattern))
  if (titlePattern) return leaf(plain('Window title matches '), literal(titlePattern))
  return leaf(plain('Any location'))
}

function dialogNoun(native?: boolean | null): string {
  if (native === true) return 'A native dialog'
  if (native === false) return 'An in-page dialog'
  return 'A dialog'
}

function describeDialog(titlePattern?: string | null, textPattern?: string | null, native?: boolean | null): ConditionNode {
  const segments: Segment[] = [plain(`${dialogNoun(native)} is open`)]
  if (titlePattern) segments.push(plain(' titled '), literal(titlePattern))
  if (textPattern) segments.push(plain(titlePattern ? ' and reading ' : ' reading '), literal(textPattern))
  return leaf(...segments)
}

function group(label: string, conditions: Condition[]): ConditionNode {
  return { segments: [plain(label)], children: conditions.map(describeCondition) }
}

export function describeCondition(condition: Condition): ConditionNode {
  switch (condition.kind) {
    case 'text_visible':
      return leaf(
        plain('Text '),
        literal(condition.pattern),
        plain(' is visible'),
        ...textMatchQualifiers(condition.regex, condition.case_sensitive),
      )
    case 'node_present':
      return leaf(literal(condition.target.description), plain(' is present'))
    case 'location_matches':
      return describeLocation(condition.pattern, condition.title_pattern)
    case 'dialog_open':
      return describeDialog(condition.title_pattern, condition.text_pattern, condition.native)
    case 'value_matches':
      return leaf(literal(condition.target.description), plain(' value matches '), literal(condition.pattern))
    case 'all_of':
      return group('All of', condition.conditions)
    case 'any_of':
      return group('Any of', condition.conditions)
    case 'not':
      return { segments: [plain('Not')], children: [describeCondition(condition.condition)] }
    default:
      return unknownCondition(condition)
  }
}

function unknownCondition(condition: never): ConditionNode {
  const kind = (condition as { kind?: string }).kind ?? 'unknown'
  console.warn('describeCondition: unrecognized condition kind', kind)
  return leaf(plain('Condition '), literal(kind))
}

/** The condition flattened to one sentence, for compact places (table cells, titles). */
export function conditionToText(condition: Condition | null | undefined): string {
  if (!condition) return ''
  return nodeToText(describeCondition(condition))
}

function nodeToText(node: ConditionNode): string {
  const head = node.segments.map((segment) => (segment.style === 'literal' ? `“${segment.text}”` : segment.text)).join('')
  if (node.children.length === 0) return head
  return `${head}: ${node.children.map(nodeToText).join('; ')}`
}

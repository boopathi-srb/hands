import type { Condition } from '../api/types'
import { describeCondition, type ConditionNode } from '../lib/conditions'

function NodeView({ node }: { node: ConditionNode }) {
  const isGroup = node.children.length > 0
  return (
    <li>
      <span className={isGroup ? 'condition-group' : undefined}>
        {node.segments.map((segment, index) =>
          segment.style === 'literal' ? (
            <code key={index} className="condition-literal">
              {segment.text}
            </code>
          ) : (
            <span key={index}>{segment.text}</span>
          ),
        )}
        {isGroup ? ':' : null}
      </span>
      {isGroup ? (
        <ul className="condition">
          {node.children.map((child, index) => (
            <NodeView key={index} node={child} />
          ))}
        </ul>
      ) : null}
    </li>
  )
}

/** A readable rendering of a condition; `emptyText` shows when there is none. */
export function ConditionView({ condition, emptyText = 'None' }: { condition: Condition | null | undefined; emptyText?: string }) {
  if (!condition) return <span className="muted">{emptyText}</span>
  return (
    <ul className="condition">
      <NodeView node={describeCondition(condition)} />
    </ul>
  )
}

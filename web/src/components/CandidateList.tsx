import type { TargetSpec } from '../api/types'
import { rankCandidates } from '../lib/candidates'
import { formatConfidence, type ConfidenceLevel } from '../lib/format'

export function ConfidenceMeter({ confidence, level }: { confidence: number; level: ConfidenceLevel }) {
  const percent = Math.round(Math.min(1, Math.max(0, confidence)) * 100)
  return (
    <div className="meter" aria-label={`Confidence ${percent} percent, ${level}`}>
      <span className="meter-value">{formatConfidence(confidence)}</span>
      <div className="meter-track" aria-hidden="true">
        <div className={`meter-fill ${level}`} style={{ width: `${percent}%` }} />
      </div>
    </div>
  )
}

/** The ranked locator candidates for one target, tried top to bottom at replay. */
export function CandidateList({ target, matchedRank }: { target: TargetSpec; matchedRank?: number | null }) {
  const ranked = rankCandidates(target.candidates)
  return (
    <ol className="candidates" aria-label={`Locator candidates for ${target.description}`}>
      {ranked.map((item) => (
        <li key={item.rank} className={`candidate ${item.isPrimary ? 'primary' : ''}`}>
          <span className="candidate-rank">#{item.rank}</span>
          <span className="row">
            <span className="chip">{item.kindLabel}</span>
            {matchedRank === item.rank - 1 ? <span className="chip info">matched</span> : null}
          </span>
          <span className="candidate-what">
            <code>{item.description}</code>
            <span className="candidate-reason">{item.candidate.reason}</span>
          </span>
          <ConfidenceMeter confidence={item.candidate.confidence} level={item.level} />
        </li>
      ))}
    </ol>
  )
}

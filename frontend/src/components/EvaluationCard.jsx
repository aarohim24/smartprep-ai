import { useState } from 'react';
import Icon from './Icon';
import styles from './EvaluationCard.module.css';

const RUBRIC_DIMS = [
  { key: 'correctness',     label: 'Correctness',     icon: 'checkCircle'  },
  { key: 'completeness',    label: 'Completeness',    icon: 'layers'       },
  { key: 'communication',   label: 'Communication',   icon: 'send'         },
  { key: 'problem_solving', label: 'Problem Solving', icon: 'brain'        },
];

export default function EvaluationCard({ evaluation }) {
  const {
    score, grade, rubric_scores,
    confidence_score, low_confidence_flag, provenance,
    strengths, improvements, ideal_answer_points,
    follow_up_question, detailed_feedback,
  } = evaluation;

  const [showProvenance, setShowProvenance] = useState(false);

  const scoreColor = score >= 8 ? 'var(--success)'  : score >= 6 ? 'var(--warn)' : 'var(--danger)';
  const scoreBg    = score >= 8 ? 'var(--success-light)' : score >= 6 ? 'var(--warn-light)' : 'var(--danger-light)';

  return (
    <div className={`${styles.card} fade-up`}>

      {/* Score row */}
      <div className={styles.scoreRow}>
        <div className={styles.grade} style={{ color: scoreColor, background: scoreBg }}>
          {grade}
        </div>
        <div className={styles.scoreBlock}>
          <span className={styles.scoreLabel}>Overall score</span>
          <div className={styles.meter}>
            <div className={styles.meterTrack}>
              <div className={styles.meterFill} style={{ width: `${score * 10}%`, background: scoreColor }} />
            </div>
            <span className={styles.scoreNum} style={{ color: scoreColor }}>{score.toFixed(1)}<span className={styles.scoreMax}>/10</span></span>
          </div>
        </div>
        <div className={styles.badges}>
          {low_confidence_flag ? (
            <div className={styles.confWarn} title={`Confidence: ${(confidence_score * 100).toFixed(0)}%`}>
              <Icon name="exclamationTriangle" size={13} /> Low confidence
            </div>
          ) : confidence_score != null && (
            <div className={styles.confGood} title={`Confidence: ${(confidence_score * 100).toFixed(0)}%`}>
              <Icon name="checkCircle" size={13} /> {Math.round(confidence_score * 100)}% confident
            </div>
          )}
        </div>
      </div>

      {/* Rubric breakdown */}
      {rubric_scores && (
        <div className={styles.rubricSection}>
          <span className={styles.rubricTitle}>Rubric breakdown</span>
          <div className={styles.rubricGrid}>
            {RUBRIC_DIMS.map(d => {
              const val = rubric_scores[d.key] ?? 0;
              const pct = (val / 10) * 100;
              const c   = val >= 7 ? 'var(--success)' : val >= 5 ? 'var(--warn)' : 'var(--danger)';
              return (
                <div key={d.key} className={styles.rubricRow}>
                  <span className={styles.rubricLabel}>
                    <Icon name={d.icon} size={13} /> {d.label}
                  </span>
                  <div className={styles.rubricBar}>
                    <div className={styles.rubricFill} style={{ width: `${pct}%`, background: c }} />
                  </div>
                  <span className={styles.rubricVal} style={{ color: c }}>{val.toFixed(1)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Detailed feedback */}
      <p className={styles.feedback}>{detailed_feedback}</p>

      {/* Strengths / Improvements */}
      <div className={styles.twoCol}>
        <div className={styles.feedSection}>
          <h4 className={styles.feedTitle} style={{ color: 'var(--success)' }}>
            <Icon name="checkCircle" size={14} /> What went well
          </h4>
          <ul className={styles.feedList}>
            {(strengths || []).map((s, i) => (
              <li key={i} className={styles.feedItem}>
                <span className={styles.dot} style={{ background: 'var(--success)' }} />{s}
              </li>
            ))}
          </ul>
        </div>
        <div className={styles.feedSection}>
          <h4 className={styles.feedTitle} style={{ color: 'var(--warn)' }}>
            <Icon name="trendingUp" size={14} /> To improve
          </h4>
          <ul className={styles.feedList}>
            {(improvements || []).map((s, i) => (
              <li key={i} className={styles.feedItem}>
                <span className={styles.dot} style={{ background: 'var(--warn)' }} />{s}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Ideal answer points */}
      {ideal_answer_points?.length > 0 && (
        <div className={styles.feedSection}>
          <h4 className={styles.feedTitle} style={{ color: 'var(--accent)' }}>
            <Icon name="lightBulb" size={14} /> Key points of a strong answer
          </h4>
          <ul className={styles.feedList}>
            {ideal_answer_points.map((p, i) => (
              <li key={i} className={styles.feedItem}>
                <span className={styles.dot} style={{ background: 'var(--accent)' }} />{p}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Follow-up */}
      {follow_up_question && (
        <div className={styles.followUp}>
          <span className={styles.followUpLabel}>
            <Icon name="informationCircle" size={13} /> Possible follow-up
          </span>
          <span className={styles.followUpText}>"{follow_up_question}"</span>
        </div>
      )}

      {/* Provenance — collapsible */}
      {provenance?.length > 0 && (
        <div className={styles.provenance}>
          <button className={styles.provenanceToggle} onClick={() => setShowProvenance(v => !v)}>
            <Icon name="paperClip" size={13} />
            {showProvenance ? 'Hide' : 'Show'} grading sources ({provenance.length})
            <Icon name={showProvenance ? 'chevronUp' : 'chevronDown'} size={13} />
          </button>
          {showProvenance && (
            <div className={styles.provenanceList}>
              {provenance.map((p, i) => (
                <div key={i} className={styles.provenanceItem}>
                  <span className={styles.provenanceDot} />
                  <span className={styles.provenanceText}>{p}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

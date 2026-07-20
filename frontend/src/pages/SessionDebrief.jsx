import { useState } from 'react';
import Icon from '../components/Icon';
import LearnerProfile from './LearnerProfile';
import styles from './SessionDebrief.module.css';

const TIER_META = {
  easy:  { label: 'Foundational', icon: 'sprout' },
  mixed: { label: 'Balanced',     icon: 'bolt'   },
  hard:  { label: 'Expert',       icon: 'fire'   },
};
const MODE_META = {
  behavioral:    { label: 'Behavioral',    icon: 'handshake' },
  coding:        { label: 'Coding',        icon: 'code'      },
  system_design: { label: 'System Design', icon: 'layers'    },
};

function RubricBar({ label, value }) {
  const pct   = (value / 10) * 100;
  const color = value >= 7 ? 'var(--success)' : value >= 5 ? 'var(--warn)' : 'var(--danger)';
  return (
    <div className={styles.rubricRow}>
      <span className={styles.rubricLabel}>{label}</span>
      <div className={styles.rubricBar}>
        <div className={styles.rubricFill} style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className={styles.rubricVal} style={{ color }}>{value.toFixed(1)}</span>
    </div>
  );
}

function ScoreRing({ score }) {
  const r     = 52;
  const circ  = 2 * Math.PI * r;
  const dash  = ((score / 10) * 100 / 100) * circ;
  const color = score >= 8 ? 'var(--success)' : score >= 6 ? 'var(--warn)' : 'var(--danger)';
  return (
    <div className={styles.ringWrap}>
      <svg width="130" height="130" viewBox="0 0 130 130">
        <circle cx="65" cy="65" r={r} fill="none" stroke="var(--bg-3)" strokeWidth="10" />
        <circle
          cx="65" cy="65" r={r} fill="none"
          stroke={color} strokeWidth="10"
          strokeDasharray={`${dash} ${circ}`}
          strokeLinecap="round"
          transform="rotate(-90 65 65)"
          style={{ transition: 'stroke-dasharray 1.2s ease' }}
        />
      </svg>
      <div className={styles.ringInner}>
        <span className={styles.ringScore} style={{ color }}>{score.toFixed(1)}</span>
        <span className={styles.ringLabel}>/ 10</span>
      </div>
    </div>
  );
}

export default function SessionDebrief({ report, sessionResults, sessionId, onRestart }) {
  const [showProfile, setShowProfile] = useState(false);

  if (!report) {
    const scores = sessionResults?.map(r => r.score) || [];
    const avg    = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : 0;
    return (
      <div className={styles.container}>
        <div className="fade-up">
          <h2 className={styles.title}>Session complete</h2>
          <p className={styles.sub}>Average score: <strong>{avg.toFixed(1)}/10</strong></p>
        </div>
        <button className={styles.restartBtn} onClick={onRestart}>
          <Icon name="refresh" size={15} /> Start a new session
        </button>
      </div>
    );
  }

  const {
    overall_score, grade, tier, mode,
    category_breakdown, strengths_summary, revisit_list,
    suggested_next_tier, improvement_focus, completion_rate,
    time_used_seconds,
  } = report;

  const gradeColor = { A: 'var(--success)', B: '#22c55e', C: 'var(--warn)', D: '#f97316', F: 'var(--danger)' }[grade] || 'var(--accent)';

  const formatTime = (secs) => {
    if (!secs) return '—';
    return `${Math.floor(secs / 60)}m ${secs % 60}s`;
  };

  const allRubrics   = category_breakdown.filter(c => c.rubric_avg);
  const globalRubric = allRubrics.length > 0 ? {
    correctness:    allRubrics.reduce((a, c) => a + c.rubric_avg.correctness,    0) / allRubrics.length,
    completeness:   allRubrics.reduce((a, c) => a + c.rubric_avg.completeness,   0) / allRubrics.length,
    communication:  allRubrics.reduce((a, c) => a + c.rubric_avg.communication,  0) / allRubrics.length,
    problem_solving:allRubrics.reduce((a, c) => a + c.rubric_avg.problem_solving,0) / allRubrics.length,
  } : null;

  const tierMeta = TIER_META[tier] || TIER_META.mixed;
  const modeMeta = MODE_META[mode] || MODE_META.behavioral;

  return (
    <div className={styles.container}>

      {/* ── Header ─────────────────────────────────────────── */}
      <div className={`${styles.header} fade-up`}>
        <div>
          <h2 className={styles.title}>Session debrief</h2>
          <div className={styles.metaRow}>
            <span className={styles.metaChip}>
              <Icon name={tierMeta.icon} size={13} /> {tierMeta.label}
            </span>
            <span className={styles.metaChip}>
              <Icon name={modeMeta.icon} size={13} /> {modeMeta.label}
            </span>
            <span className={styles.metaChip}>
              <Icon name="clock" size={13} /> {formatTime(time_used_seconds)}
            </span>
            <span className={styles.metaChip}>
              <Icon name="chartBar" size={13} /> {Math.round(completion_rate * 100)}% completed
            </span>
          </div>
        </div>
        <div className={styles.gradeBadge} style={{ color: gradeColor }}>
          {grade}
        </div>
      </div>

      {/* ── Score + Rubric ──────────────────────────────────── */}
      <div className={`${styles.scoreRow} fade-up-1`}>
        <div className={styles.scorePanel}>
          <ScoreRing score={overall_score} />
          <span className={styles.overallLabel}>Overall score</span>
        </div>
        {globalRubric && (
          <div className={styles.rubricPanel}>
            <span className={styles.rubricTitle}>Average rubric breakdown</span>
            <div className={styles.rubricGrid}>
              <RubricBar label="Correctness"     value={globalRubric.correctness}    />
              <RubricBar label="Completeness"    value={globalRubric.completeness}   />
              <RubricBar label="Communication"   value={globalRubric.communication}  />
              <RubricBar label="Problem Solving" value={globalRubric.problem_solving}/>
            </div>
          </div>
        )}
      </div>

      {/* ── Category breakdown ──────────────────────────────── */}
      <div className={`${styles.section} fade-up-2`}>
        <h3 className={styles.sectionTitle}>
          <Icon name="chartBar" size={16} /> By category
        </h3>
        <div className={styles.categoryList}>
          {category_breakdown.map(c => {
            const color = c.avg_score >= 7 ? 'var(--success)' : c.avg_score >= 5 ? 'var(--warn)' : 'var(--danger)';
            return (
              <div key={c.category} className={styles.categoryRow}>
                <span className={styles.categoryName}>{c.category}</span>
                <div className={styles.categoryBar}>
                  <div
                    className={styles.categoryFill}
                    style={{ width: `${(c.avg_score / 10) * 100}%`, background: color }}
                  />
                </div>
                <span className={styles.categoryScore} style={{ color }}>{c.avg_score}/10</span>
                <span className={styles.categoryCount}>{c.question_count}q</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Insights ────────────────────────────────────────── */}
      <div className={`${styles.twoCol} fade-up-3`}>
        <div className={styles.insightPanel}>
          <h3 className={styles.insightTitle} style={{ color: 'var(--success)' }}>
            <Icon name="checkCircle" size={16} /> What went well
          </h3>
          <ul className={styles.insightList}>
            {strengths_summary.map((s, i) => (
              <li key={i} className={styles.insightItem}>
                <span className={styles.insightDot} style={{ background: 'var(--success)' }} />{s}
              </li>
            ))}
          </ul>
        </div>
        <div className={styles.insightPanel}>
          <h3 className={styles.insightTitle} style={{ color: 'var(--warn)' }}>
            <Icon name="trendingUp" size={16} /> Focus areas
          </h3>
          <ul className={styles.insightList}>
            {improvement_focus.map((s, i) => (
              <li key={i} className={styles.insightItem}>
                <span className={styles.insightDot} style={{ background: 'var(--warn)' }} />{s}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* ── Revisit list ────────────────────────────────────── */}
      {revisit_list.length > 0 && (
        <div className={`${styles.section} fade-up-3`}>
          <h3 className={styles.sectionTitle}>
            <Icon name="refresh" size={16} /> Questions to revisit
          </h3>
          <div className={styles.revisitList}>
            {revisit_list.map((r, i) => (
              <div key={i} className={styles.revisitItem}>
                <Icon name="xCircle" size={14} style={{ color: 'var(--danger)', flexShrink: 0 }} />
                <span>{r}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Next session ────────────────────────────────────── */}
      <div className={`${styles.nextSection} fade-up-4`}>
        <h3 className={styles.nextTitle}>Recommended next session</h3>
        <div className={styles.nextTier}>
          <div className={styles.nextTierIconWrap}>
            <Icon name={(TIER_META[suggested_next_tier] || TIER_META.mixed).icon} size={20} />
          </div>
          <div>
            <span className={styles.nextTierName}>
              {(TIER_META[suggested_next_tier] || TIER_META.mixed).label} tier
            </span>
            <span className={styles.nextTierSub}>
              {overall_score >= 8
                ? 'Excellent performance — push to the next challenge.'
                : overall_score >= 6
                  ? 'Solid work — stay at this tier or step up.'
                  : 'Keep drilling the fundamentals before moving up.'}
            </span>
          </div>
        </div>
      </div>

      {/* ── Learner profile ─────────────────────────────────── */}
      {showProfile && sessionId && (
        <div className={`${styles.profilePanel} fade-up`}>
          <LearnerProfile sessionId={sessionId} onClose={() => setShowProfile(false)} />
        </div>
      )}

      {/* ── Actions ─────────────────────────────────────────── */}
      <div className={`${styles.actions} fade-up-4`}>
        {sessionId && (
          <button
            id="view-learner-profile-btn"
            className={styles.profileBtn}
            onClick={() => setShowProfile(v => !v)}
          >
            <Icon name={showProfile ? 'chevronUp' : 'chartBar'} size={15} />
            {showProfile ? 'Hide progress' : 'View my progress'}
          </button>
        )}
        <button id="start-new-session-btn" className={styles.restartBtn} onClick={onRestart}>
          <Icon name="refresh" size={15} />
          New session
        </button>
      </div>
    </div>
  );
}

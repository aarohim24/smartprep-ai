import { useState, useEffect } from 'react';
import { api } from '../services/api';
import styles from './LearnerProfile.module.css';

const DIM_LABELS = {
  correctness: { label: 'Correctness', icon: '✓', color: '#2563eb' },
  completeness: { label: 'Completeness', icon: '◉', color: '#7c3aed' },
  communication: { label: 'Communication', icon: '💬', color: '#0d9488' },
  problem_solving: { label: 'Problem Solving', icon: '🧠', color: '#d97706' },
};

const TIER_ICONS = { easy: '🌱', mixed: '⚡', hard: '🔥' };
const MODE_ICONS = { behavioral: '🤝', coding: '💻', system_design: '🏗️' };

function DimBar({ value, color, label, icon }) {
  const pct = (value / 10) * 100;
  const textColor = value >= 7 ? '#16a34a' : value >= 5 ? '#d97706' : '#dc2626';
  return (
    <div className={styles.dimRow}>
      <span className={styles.dimLabel}>{icon} {label}</span>
      <div className={styles.dimBar}>
        <div className={styles.dimFill} style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className={styles.dimVal} style={{ color: textColor }}>{value.toFixed(1)}</span>
    </div>
  );
}

function SkillCard({ skill, dimensions }) {
  const avgScore = dimensions.reduce((s, d) => s + d.avg_score, 0) / dimensions.length;
  const color = avgScore >= 7 ? '#16a34a' : avgScore >= 5 ? '#d97706' : '#dc2626';
  return (
    <div className={styles.skillCard}>
      <div className={styles.skillHeader}>
        <span className={styles.skillName}>{skill}</span>
        <span className={styles.skillAvg} style={{ color }}>
          {avgScore.toFixed(1)}/10
        </span>
      </div>
      {dimensions.map(d => {
        const meta = DIM_LABELS[d.dimension] || { label: d.dimension, icon: '·', color: '#888' };
        return (
          <DimBar
            key={d.dimension}
            value={d.avg_score}
            color={meta.color}
            label={meta.label}
            icon={meta.icon}
          />
        );
      })}
    </div>
  );
}

function FSRSCard({ card }) {
  const now = Date.now() / 1000;
  const overdue = card.due_at < now;
  const daysUntil = Math.max(0, (card.due_at - now) / 86400);
  return (
    <div className={`${styles.fsrsCard} ${overdue ? styles.fsrsOverdue : ''}`}>
      <div className={styles.fsrsHeader}>
        <span className={styles.fsrsCategory}>{card.category} · {card.difficulty}</span>
        {overdue
          ? <span className={styles.frssDueBadge}>📬 Due now</span>
          : <span className={styles.fsrsFutureBadge}>⏳ in {daysUntil.toFixed(1)}d</span>
        }
      </div>
      <p className={styles.fsrsQuestion}>{card.question}</p>
      <span className={styles.fsrsLastScore}>Last score: {card.last_score?.toFixed(1) ?? '—'}/10</span>
    </div>
  );
}

function TrajectoryChart({ trajectory }) {
  if (!trajectory.length) return null;
  const maxScore = 10;
  const width = 440;
  const height = 120;
  const pad = 20;
  const pts = trajectory.map((t, i) => {
    const x = pad + (i / Math.max(trajectory.length - 1, 1)) * (width - 2 * pad);
    const y = height - pad - ((t.overall_score ?? 5) / maxScore) * (height - 2 * pad);
    return { x, y, t };
  });

  const polyline = pts.map(p => `${p.x},${p.y}`).join(' ');

  return (
    <div className={styles.trajectoryWrap}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={styles.trajectorySvg}>
        {/* Grid lines */}
        {[2, 4, 6, 8, 10].map(v => {
          const y = height - pad - (v / maxScore) * (height - 2 * pad);
          return (
            <g key={v}>
              <line x1={pad} y1={y} x2={width - pad} y2={y} stroke="var(--border)" strokeDasharray="3 3" />
              <text x={pad - 4} y={y + 4} fontSize="9" fill="var(--text-3)" textAnchor="end">{v}</text>
            </g>
          );
        })}
        {/* Area fill */}
        <polygon
          points={[
            `${pts[0].x},${height - pad}`,
            ...pts.map(p => `${p.x},${p.y}`),
            `${pts[pts.length - 1].x},${height - pad}`,
          ].join(' ')}
          fill="rgba(37,99,235,0.08)"
        />
        {/* Line */}
        <polyline points={polyline} fill="none" stroke="#2563eb" strokeWidth="2" strokeLinejoin="round" />
        {/* Dots */}
        {pts.map((p, i) => (
          <g key={i}>
            <circle cx={p.x} cy={p.y} r={4} fill="white" stroke="#2563eb" strokeWidth="2" />
            <title>{`Session ${i + 1}: ${p.t.overall_score?.toFixed(1) ?? '?'}/10 · ${p.t.mode} · ${p.t.tier}`}</title>
          </g>
        ))}
      </svg>
      <div className={styles.trajectoryLegend}>
        {pts.map((p, i) => (
          <div key={i} className={styles.trajectoryTick}>
            <span>{MODE_ICONS[p.t.mode] || ''}{TIER_ICONS[p.t.tier] || ''}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function LearnerProfile({ sessionId, onClose }) {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError('');
      try {
        const data = await api.getLearnerProfile(sessionId);
        if (!cancelled) setProfile(data);
      } catch (e) {
        if (!cancelled) setError(e.message || 'Could not load profile.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [sessionId]);

  if (loading) return (
    <div className={styles.loading}>
      <span className={styles.spinner} />
      <span>Loading your learner profile...</span>
    </div>
  );

  if (error) return (
    <div className={styles.error}>
      <p>⚠️ {error}</p>
      {onClose && <button className={styles.closeBtn} onClick={onClose}>Close</button>}
    </div>
  );

  if (!profile) return null;

  // Group weakness graph by skill
  const bySkill = {};
  for (const node of profile.weakness_graph || []) {
    if (!bySkill[node.skill]) bySkill[node.skill] = [];
    bySkill[node.skill].push(node);
  }
  const skills = Object.entries(bySkill).sort((a, b) => {
    const avgA = a[1].reduce((s, d) => s + d.avg_score, 0) / a[1].length;
    const avgB = b[1].reduce((s, d) => s + d.avg_score, 0) / b[1].length;
    return avgA - avgB; // weakest first
  });

  const dueCards = profile.fsrs_due || [];
  const trajectory = profile.trajectory || [];

  return (
    <div className={styles.container}>
      <div className={styles.profileHeader}>
        <div>
          <h2 className={styles.title}>Learner Profile</h2>
          <p className={styles.sub}>{profile.session_count} session{profile.session_count !== 1 ? 's' : ''} tracked</p>
        </div>
        {onClose && (
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        )}
      </div>

      {/* Cross-session trajectory */}
      {trajectory.length > 1 && (
        <div className={`${styles.section} fade-up`}>
          <h3 className={styles.sectionTitle}>Score trajectory (last {trajectory.length} sessions)</h3>
          <TrajectoryChart trajectory={trajectory} />
        </div>
      )}

      {/* Weakness graph */}
      {skills.length > 0 ? (
        <div className={`${styles.section} fade-up-1`}>
          <h3 className={styles.sectionTitle}>Skill breakdown</h3>
          <p className={styles.sectionSub}>Sorted weakest → strongest. Each bar is an EMA across all your sessions.</p>
          <div className={styles.skillGrid}>
            {skills.map(([skill, dims]) => (
              <SkillCard key={skill} skill={skill} dimensions={dims} />
            ))}
          </div>
        </div>
      ) : (
        <div className={styles.empty}>
          No skill data yet. Complete a session to populate your weakness graph.
        </div>
      )}

      {/* FSRS due cards */}
      {dueCards.length > 0 && (
        <div className={`${styles.section} fade-up-2`}>
          <h3 className={styles.sectionTitle}>
            📬 Spaced revision due ({dueCards.length})
          </h3>
          <p className={styles.sectionSub}>
            These questions scored {'<'}7 and are due for review based on your forgetting curve.
          </p>
          <div className={styles.fsrsList}>
            {dueCards.map((c, i) => (
              <FSRSCard key={i} card={c} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

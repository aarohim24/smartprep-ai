import { useState } from 'react';
import { api } from '../services/api';
import Icon from '../components/Icon';
import styles from './JobDescription.module.css';

const LEVELS = [
  { value: 'junior', label: 'Junior',  sub: '0 – 2 yrs' },
  { value: 'mid',    label: 'Mid',     sub: '2 – 5 yrs' },
  { value: 'senior', label: 'Senior',  sub: '5 – 8 yrs' },
  { value: 'lead',   label: 'Lead',    sub: '8+ yrs'    },
];

const TIERS = [
  {
    value: 'easy',
    label: 'Foundational',
    description: '5 questions · 15 min',
    icon: 'sprout',
    detail: 'Core concepts and fundamentals. Great for warming up.',
    color: '#2f9e44',
    bg: '#ebfbee',
    border: '#b2f2bb',
  },
  {
    value: 'mixed',
    label: 'Balanced',
    description: '7 questions · 25 min',
    icon: 'bolt',
    detail: '30% easy, 40% medium, 30% hard. The full range.',
    color: '#e67700',
    bg: '#fff9db',
    border: '#ffe066',
  },
  {
    value: 'hard',
    label: 'Expert',
    description: '10 questions · 35 min',
    icon: 'fire',
    detail: 'Deep technical depth, edge cases, system-level trade-offs.',
    color: '#e03131',
    bg: '#fff5f5',
    border: '#ffc9c9',
  },
];

const MODES = [
  {
    value: 'behavioral',
    label: 'Behavioral',
    icon: 'handshake',
    sub: 'STAR method · leadership · collaboration',
  },
  {
    value: 'coding',
    label: 'Coding',
    icon: 'code',
    sub: 'Algorithms · complexity · implementation',
  },
  {
    value: 'system_design',
    label: 'System Design',
    icon: 'layers',
    sub: 'Architecture · scalability · trade-offs',
  },
];

export default function JobDescription({ sessionId, skills, onSuccess, onBack }) {
  const [jd, setJd]         = useState('');
  const [level, setLevel]   = useState('junior');
  const [tier, setTier]     = useState('mixed');
  const [mode, setMode]     = useState('behavioral');
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState('');

  const handleSubmit = async () => {
    if (jd.trim().length < 50) {
      setError('Please add more detail to the job description (at least 50 characters).');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const result = await api.generateQuestions({
        session_id: sessionId,
        job_description: jd,
        experience_level: level,
        tier,
        mode,
      });
      onSuccess(result);
    } catch (e) {
      setError(e.message || 'Failed to generate questions. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      <div className="fade-up">
        <h2 className={styles.title}>Configure your session</h2>
        <p className={styles.sub}>
          Paste the role you're preparing for, then choose your interview mode and difficulty.
        </p>
      </div>

      {/* Detected skills */}
      {skills.length > 0 && (
        <div className={`${styles.skillsBox} fade-up-1`}>
          <span className={styles.skillsLabel}>Skills detected from your resume</span>
          <div className={styles.skillTags}>
            {skills.map(s => <span key={s} className={styles.tag}>{s}</span>)}
          </div>
        </div>
      )}

      {/* Job description */}
      <div className={`${styles.field} fade-up-1`}>
        <label className={styles.label} htmlFor="jd-input">Job description</label>
        <textarea
          id="jd-input"
          className={styles.textarea}
          rows={7}
          placeholder="Paste the job description here — include responsibilities, requirements, and tech stack for more accurate questions."
          value={jd}
          onChange={(e) => setJd(e.target.value)}
        />
        <span className={styles.charCount}>{jd.length} characters</span>
      </div>

      {/* Interview Mode */}
      <div className={`${styles.section} fade-up-2`}>
        <label className={styles.label}>Interview mode</label>
        <div className={styles.modeGrid}>
          {MODES.map(m => (
            <button
              key={m.value}
              id={`mode-${m.value}`}
              className={`${styles.modeBtn} ${mode === m.value ? styles.modeBtnActive : ''}`}
              onClick={() => setMode(m.value)}
            >
              <span className={styles.modeIcon}>
                <Icon name={m.icon} size={20} />
              </span>
              <span className={styles.modeName}>{m.label}</span>
              <span className={styles.modeSub}>{m.sub}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Difficulty Tier */}
      <div className={`${styles.section} fade-up-2`}>
        <label className={styles.label}>Difficulty tier</label>
        <div className={styles.tierGrid}>
          {TIERS.map(t => (
            <button
              key={t.value}
              id={`tier-${t.value}`}
              className={`${styles.tierBtn} ${tier === t.value ? styles.tierBtnActive : ''}`}
              onClick={() => setTier(t.value)}
              style={tier === t.value
                ? { borderColor: t.color, background: t.bg }
                : {}
              }
            >
              <span className={styles.tierIconWrap} style={tier === t.value ? { color: t.color } : {}}>
                <Icon name={t.icon} size={18} />
              </span>
              <span className={styles.tierLabel} style={tier === t.value ? { color: t.color } : {}}>
                {t.label}
              </span>
              <span className={styles.tierDescription}>{t.description}</span>
              <span className={styles.tierDetail}>{t.detail}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Experience Level */}
      <div className={`${styles.section} fade-up-3`}>
        <label className={styles.label}>Experience level</label>
        <div className={styles.levelGrid}>
          {LEVELS.map(l => (
            <button
              key={l.value}
              id={`level-${l.value}`}
              className={`${styles.levelBtn} ${level === l.value ? styles.levelActive : ''}`}
              onClick={() => setLevel(l.value)}
            >
              <span className={styles.levelLabel}>{l.label}</span>
              <span className={styles.levelSub}>{l.sub}</span>
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className={`${styles.error} fade-up`}>
          <Icon name="exclamationTriangle" size={15} />
          {error}
        </div>
      )}

      {loading && (
        <div className={styles.loadingBox}>
          <span className="spinner spinner-lg" />
          <div>
            <p className={styles.loadingTitle}>Generating your questions…</p>
            <p className={styles.loadingHint}>This usually takes 5–15 seconds</p>
          </div>
        </div>
      )}

      <div className={`${styles.actions} fade-up-4`}>
        <button className={styles.backBtn} onClick={onBack}>
          <Icon name="arrowLeft" size={15} />
          Back
        </button>
        <button
          id="generate-questions-btn"
          className={styles.submitBtn}
          disabled={!jd.trim() || loading}
          onClick={handleSubmit}
        >
          {loading ? 'Generating…' : <>Start session <Icon name="arrowRight" size={16} /></>}
        </button>
      </div>
    </div>
  );
}

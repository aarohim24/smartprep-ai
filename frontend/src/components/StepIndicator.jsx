import Icon from './Icon';
import styles from './StepIndicator.module.css';

export default function StepIndicator({ steps, current }) {
  return (
    <div className={styles.wrapper}>
      {steps.map((label, i) => {
        const done   = i < current;
        const active = i === current;
        return (
          <div key={i} className={styles.item}>
            <div className={`${styles.circle} ${done ? styles.done : ''} ${active ? styles.active : ''}`}>
              {done
                ? <Icon name="checkCircle" size={14} />
                : <span>{i + 1}</span>
              }
            </div>
            <span className={`${styles.label} ${active ? styles.activeLabel : ''} ${done ? styles.doneLabel : ''}`}>
              {label}
            </span>
            {i < steps.length - 1 && (
              <div className={`${styles.line} ${done ? styles.lineDone : ''}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

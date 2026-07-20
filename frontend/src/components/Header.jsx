import Icon from './Icon';
import styles from './Header.module.css';

export default function Header({ onRestart }) {
  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <div className={styles.logo}>
          <div className={styles.logoMark}>
            <Icon name="bolt" size={16} />
          </div>
          <span className={styles.logoText}>SmartPrep</span>
          <span className={styles.logoBadge}>AI</span>
        </div>
        {onRestart && (
          <button className={styles.restartBtn} onClick={onRestart} title="Start a new session">
            <Icon name="refresh" size={15} />
            <span>New session</span>
          </button>
        )}
      </div>
    </header>
  );
}

import { useState, useCallback } from 'react';
import Header from './components/Header';
import StepIndicator from './components/StepIndicator';
import ResumeUpload from './pages/ResumeUpload';
import JobDescription from './pages/JobDescription';
import Questions from './pages/Questions';
import SessionDebrief from './pages/SessionDebrief';
import styles from './App.module.css';

const STEPS = ['Upload Resume', 'Configure', 'Interview', 'Debrief'];

const INITIAL_STATE = {
  step: 0,
  sessionId: null,
  skills: [],
  questions: [],
  jobRole: '',
  keyRequirements: [],
  tier: 'mixed',
  mode: 'behavioral',
  timerSeconds: 25 * 60,
  sessionResults: [],
  debriefReport: null,
};

export default function App() {
  const [state, setState] = useState(INITIAL_STATE);
  const {
    step, sessionId, skills, questions, jobRole, keyRequirements,
    tier, mode, timerSeconds, sessionResults, debriefReport,
  } = state;

  const handleResumeUploaded = useCallback(({ session_id, skills_detected }) => {
    setState(prev => ({
      ...prev,
      step: 1,
      sessionId: session_id,
      skills: skills_detected || [],
    }));
  }, []);

  const handleQuestionsGenerated = useCallback(({ questions, job_role, key_requirements, tier, mode, timer_seconds }) => {
    setState(prev => ({
      ...prev,
      step: 2,
      questions,
      jobRole: job_role,
      keyRequirements: key_requirements || [],
      tier: tier || 'mixed',
      mode: mode || 'behavioral',
      timerSeconds: timer_seconds || 25 * 60,
    }));
  }, []);

  const handleSessionComplete = useCallback((results, report) => {
    setState(prev => ({
      ...prev,
      step: 3,
      sessionResults: results,
      debriefReport: report,
    }));
  }, []);

  const handleRestart = useCallback(() => {
    setState(INITIAL_STATE);
  }, []);

  const handleBack = useCallback(() => {
    setState(prev => ({ ...prev, step: 0 }));
  }, []);

  return (
    <div className={styles.app}>
      <Header onRestart={step > 0 ? handleRestart : null} />
      <main className={styles.main}>
        <StepIndicator steps={STEPS} current={step} />
        <div className={styles.content}>
          {step === 0 && (
            <ResumeUpload onSuccess={handleResumeUploaded} />
          )}
          {step === 1 && (
            <JobDescription
              sessionId={sessionId}
              skills={skills}
              onSuccess={handleQuestionsGenerated}
              onBack={handleBack}
            />
          )}
          {step === 2 && (
            <Questions
              sessionId={sessionId}
              questions={questions}
              jobRole={jobRole}
              keyRequirements={keyRequirements}
              tier={tier}
              mode={mode}
              timerSeconds={timerSeconds}
              onComplete={handleSessionComplete}
              onRestart={handleRestart}
            />
          )}
          {step === 3 && (
            <SessionDebrief
              report={debriefReport}
              sessionResults={sessionResults}
              sessionId={sessionId}
              onRestart={handleRestart}
            />
          )}
        </div>
      </main>
    </div>
  );
}

import { useState, useRef, useCallback } from 'react';
import Icon from './Icon';
import styles from './VoiceRecorder.module.css';

const FILLER_WORDS = ['um', 'uh', 'like', 'you know', 'basically', 'literally', 'actually', 'so'];

export default function VoiceRecorder({ onTranscript, onMetrics }) {
  const [isRecording, setIsRecording] = useState(false);
  const [supported] = useState(() => !!(window.SpeechRecognition || window.webkitSpeechRecognition));
  const recognitionRef = useRef(null);
  const metricsRef    = useRef({ fillerCount: 0, wordCount: 0, pauseCount: 0, startTime: null, lastSpeechTime: null });

  const startRecording = useCallback(() => {
    if (!supported) return;
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.continuous      = true;
    recognition.interimResults  = false;
    recognition.lang            = 'en-US';
    recognitionRef.current      = recognition;
    metricsRef.current = { fillerCount: 0, wordCount: 0, pauseCount: 0, startTime: Date.now(), lastSpeechTime: Date.now() };

    recognition.onresult = (event) => {
      const now = Date.now();
      if (metricsRef.current.lastSpeechTime && now - metricsRef.current.lastSpeechTime > 2000) {
        metricsRef.current.pauseCount++;
      }
      metricsRef.current.lastSpeechTime = now;

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript.trim();
        const words      = transcript.toLowerCase().split(/\s+/);
        let fillerCount  = 0;
        for (const filler of FILLER_WORDS) {
          const matches = transcript.match(new RegExp(`\\b${filler}\\b`, 'gi'));
          if (matches) fillerCount += matches.length;
        }
        metricsRef.current.fillerCount += fillerCount;
        metricsRef.current.wordCount   += words.length;
        onTranscript(' ' + transcript);
      }
    };

    recognition.onerror = (event) => {
      if (event.error !== 'no-speech') console.warn('SpeechRecognition error:', event.error);
    };

    recognition.onend = () => {
      if (isRecording && recognitionRef.current) {
        try { recognitionRef.current.start(); } catch (_) {}
      }
    };

    recognition.start();
    setIsRecording(true);
  }, [supported, onTranscript, isRecording]);

  const stopRecording = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.onend = null;
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    setIsRecording(false);
    const { fillerCount, wordCount, pauseCount, startTime } = metricsRef.current;
    const durationSeconds = startTime ? (Date.now() - startTime) / 1000 : 1;
    const wpm = wordCount > 0 ? Math.round((wordCount / durationSeconds) * 60) : 0;
    onMetrics?.({ filler_word_count: fillerCount, wpm: Math.min(wpm, 300), pause_count: pauseCount });
  }, [onMetrics]);

  if (!supported) return null;

  return (
    <div className={styles.recorder}>
      <button
        type="button"
        id="voice-recorder-btn"
        className={`${styles.micBtn} ${isRecording ? styles.micActive : ''}`}
        onClick={isRecording ? stopRecording : startRecording}
        title={isRecording ? 'Stop recording' : 'Record answer with microphone'}
      >
        {isRecording ? (
          <>
            <span className={styles.pulse} />
            <Icon name="microphoneOff" size={15} />
            <span>Stop</span>
          </>
        ) : (
          <>
            <Icon name="microphone" size={15} />
            <span>Record</span>
          </>
        )}
      </button>
      {isRecording && (
        <span className={styles.recStatus}>Listening — speak your answer</span>
      )}
    </div>
  );
}

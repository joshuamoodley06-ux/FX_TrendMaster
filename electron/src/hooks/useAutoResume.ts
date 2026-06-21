import { useCallback, useEffect, useRef, useState } from 'react';
import {
  readAutoResumeSession,
  writeAutoResumeSession,
  type AutoResumeSession,
} from '../autoResumeStorage';

export type AutoResumePhase = 'booting' | 'welcome' | 'loading' | 'ready';

export type UseAutoResumeArgs = {
  symbol: string;
  timeframe: string;
  onResume: (session: AutoResumeSession) => Promise<void>;
  onSymbolChange?: (symbol: string) => void;
  onTimeframeChange?: (timeframe: string) => void;
};

export type UseAutoResumeResult = {
  phase: AutoResumePhase;
  isAutoResuming: boolean;
  isWelcome: boolean;
  sessionReady: boolean;
  storedSession: AutoResumeSession | null;
  beginFirstSession: () => Promise<void>;
  markSessionActive: (symbol: string, timeframe: string) => void;
};

export function useAutoResume(args: UseAutoResumeArgs): UseAutoResumeResult {
  const [phase, setPhase] = useState<AutoResumePhase>('booting');
  const [storedSession, setStoredSession] = useState<AutoResumeSession | null>(null);
  const startedRef = useRef(false);
  const resumeRef = useRef(args.onResume);
  resumeRef.current = args.onResume;

  const runResume = useCallback(async (session: AutoResumeSession) => {
    setPhase('loading');
    setStoredSession(session);
    if (session.symbol !== args.symbol) args.onSymbolChange?.(session.symbol);
    if (session.timeframe !== args.timeframe) args.onTimeframeChange?.(session.timeframe);
    await resumeRef.current(session);
    setPhase('ready');
  }, [args.symbol, args.timeframe, args.onSymbolChange, args.onTimeframeChange]);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    const session = readAutoResumeSession();
    if (!session) {
      setPhase('welcome');
      return;
    }

    void runResume(session).catch(() => {
      setPhase('ready');
    });
  }, [runResume]);

  const beginFirstSession = useCallback(async () => {
    const session = {
      symbol: String(args.symbol || 'XAUUSD').toUpperCase(),
      timeframe: String(args.timeframe || 'D1').toUpperCase(),
    };
    writeAutoResumeSession(session.symbol, session.timeframe);
    await runResume(session);
  }, [args.symbol, args.timeframe, runResume]);

  const markSessionActive = useCallback((symbol: string, timeframe: string) => {
    writeAutoResumeSession(symbol, timeframe);
    setStoredSession({ symbol: symbol.toUpperCase(), timeframe: timeframe.toUpperCase() });
    if (phase === 'welcome') setPhase('ready');
  }, [phase]);

  return {
    phase,
    isAutoResuming: phase === 'loading',
    isWelcome: phase === 'welcome',
    sessionReady: phase === 'ready',
    storedSession,
    beginFirstSession,
    markSessionActive,
  };
}

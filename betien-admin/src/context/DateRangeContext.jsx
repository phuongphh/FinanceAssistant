import { createContext, useCallback, useContext, useMemo, useState } from 'react';

export const DATE_RANGES = [
  { value: '7d', label: '7 ngày', days: 7 },
  { value: '14d', label: '14 ngày', days: 14 },
  { value: '30d', label: '30 ngày', days: 30 },
  { value: '90d', label: '90 ngày', days: 90 },
];

const DateRangeContext = createContext(null);

export function DateRangeProvider({ children }) {
  const [range, setRange] = useState('30d');
  const [refreshNonce, setRefreshNonce] = useState(0);
  const selectedRange = DATE_RANGES.find((item) => item.value === range) || DATE_RANGES[2];
  const refresh = useCallback(() => setRefreshNonce((value) => value + 1), []);
  const value = useMemo(() => ({ range, setRange, selectedRange, refresh, refreshNonce }), [range, selectedRange, refresh, refreshNonce]);
  return <DateRangeContext.Provider value={value}>{children}</DateRangeContext.Provider>;
}

export function useDateRange() {
  const context = useContext(DateRangeContext);
  if (!context) throw new Error('useDateRange must be used inside DateRangeProvider');
  return context;
}

import React, { createContext, useContext } from 'react';

export type CockpitOverviewContextValue = {
  overviewMaps: React.ReactNode;
  overviewPlanning?: React.ReactNode;
  brain: any;
  symbol: string;
};

const CockpitOverviewContext = createContext<CockpitOverviewContextValue | null>(null);

export function CockpitOverviewProvider({
  value,
  children,
}: {
  value: CockpitOverviewContextValue;
  children: React.ReactNode;
}) {
  return <CockpitOverviewContext.Provider value={value}>{children}</CockpitOverviewContext.Provider>;
}

export function useCockpitOverview(): CockpitOverviewContextValue | null {
  return useContext(CockpitOverviewContext);
}

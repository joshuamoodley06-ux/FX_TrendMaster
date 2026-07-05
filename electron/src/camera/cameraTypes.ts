export type CameraIntent = 'LATEST' | 'FIT_ALL' | 'CASE' | 'REPLAY' | 'RANGE' | 'FIT_STRUCTURAL_RANGE' | 'RESTORE_LOCKED' | 'PRESERVE_OR_NEAREST_TIME' | 'HORIZONTAL_STRETCH' | 'VERTICAL_STRETCH' | 'NONE';

export type StructuralFitWindow = {
  start: string;
  end: string;
  low: number;
  high: number;
  padRatio?: number;
};

export type CameraCommand = {
  intent: CameraIntent;
  token: number;
  targetTime?: string | null;
  reason?: string;
  scaleFactor?: number;
  fitWindow?: StructuralFitWindow | null;
  priceDomain?: { low: number; high: number } | null;
};

export type VisibleCameraDomain = {
  start: string;
  end: string;
  priceLow: number;
  priceHigh: number;
  visibleBars?: number;
  barSpacingPx?: number;
};

export type CameraMode = 'AUTO' | 'LOCKED' | 'CASE' | 'REPLAY';

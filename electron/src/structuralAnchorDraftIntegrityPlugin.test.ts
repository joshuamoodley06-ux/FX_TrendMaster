import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { applyStructuralAnchorDraftIntegrity } from '../build/structuralAnchorDraftIntegrityPlugin';

describe('structuralAnchorDraftIntegrityPlugin', () => {
  it('applies every guarded main.tsx hunk to the stable baseline source', () => {
    const source = readFileSync(new URL('./main.tsx', import.meta.url), 'utf8');
    const transformed = applyStructuralAnchorDraftIntegrity(source);

    expect(transformed).toContain("from './structuralRangeDraftSession'");
    expect(transformed).toContain('const structuralRangeDraftSessionRef');
    expect(transformed).toContain('captureStructuralRangeDraftSnapshot');
  });

  it('is idempotent when Vite presents already transformed source', () => {
    const source = readFileSync(new URL('./main.tsx', import.meta.url), 'utf8');
    const once = applyStructuralAnchorDraftIntegrity(source);
    expect(applyStructuralAnchorDraftIntegrity(once)).toBe(once);
  });
});

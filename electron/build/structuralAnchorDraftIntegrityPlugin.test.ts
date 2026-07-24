import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { applyStructuralAnchorDraftIntegrity } from './structuralAnchorDraftIntegrityPlugin';

describe('structuralAnchorDraftIntegrityPlugin', () => {
  it('applies every guarded main.tsx hunk to the stable baseline source', () => {
    const source = readFileSync(new URL('../src/main.tsx', import.meta.url), 'utf8');
    const transformed = applyStructuralAnchorDraftIntegrity(source);

    expect(transformed).toContain("from './structuralRangeDraftSession'");
    expect(transformed).toContain('const structuralRangeDraftSessionRef');
    expect(transformed).toContain('captureStructuralRangeDraftSnapshot');
    expect(transformed).toContain('an older RL cannot be reused');
    expect(transformed).toContain('an older RH cannot be reused');
  });

  it('is idempotent when Vite presents already transformed source', () => {
    const source = readFileSync(new URL('../src/main.tsx', import.meta.url), 'utf8');
    const once = applyStructuralAnchorDraftIntegrity(source);
    expect(applyStructuralAnchorDraftIntegrity(once)).toBe(once);
  });
});

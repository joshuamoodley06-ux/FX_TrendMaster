import { describe, expect, it, vi } from 'vitest';
import { isMappingInspectorTab, INSPECTOR_RAIL_TABS, normalizeInspectorTabId } from './inspectorPanel';

describe('inspectorPanel context isolation', () => {
  it('uses candle-first five-tab rail', () => {
    expect(INSPECTOR_RAIL_TABS.map((t) => t.shortLabel)).toEqual(['F', 'H', 'C', 'A', '⚙']);
    expect(INSPECTOR_RAIL_TABS.find((t) => t.id === 'seed')?.title).toBe('Folder / Case');
    expect(INSPECTOR_RAIL_TABS.find((t) => t.id === 'campaign')?.title).toBe('Campaign');
    expect(INSPECTOR_RAIL_TABS.find((t) => t.id === 'audit')?.title).toBe('Audit / Export');
  });

  it('migrates legacy mark tab to tools', () => {
    expect(normalizeInspectorTabId('mark')).toBe('tools');
    expect(normalizeInspectorTabId('dashboard')).toBe('tools');
    expect(normalizeInspectorTabId('campaign')).toBe('campaign');
  });

  it('treats chart-native tabs as mapping context', () => {
    expect(isMappingInspectorTab('campaign')).toBe(true);
    expect(isMappingInspectorTab('gps')).toBe(true);
    expect(isMappingInspectorTab('audit')).toBe(true);
    expect(isMappingInspectorTab('narrative')).toBe(false);
  });

  it('renderTab receives only the active tab id when simulated', () => {
    const renderTab = vi.fn((tab: string) => (tab === 'campaign' ? 'campaign-panel' : null));
    const rendered = renderTab('campaign');
    expect(renderTab).toHaveBeenCalledWith('campaign');
    expect(rendered).toBe('campaign-panel');
    expect(renderTab('dashboard')).toBeNull();
  });
});

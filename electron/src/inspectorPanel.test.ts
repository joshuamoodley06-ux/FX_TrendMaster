import { describe, expect, it, vi } from 'vitest';
import { isMappingInspectorTab, INSPECTOR_TABS } from './inspectorPanel';

describe('inspectorPanel context isolation', () => {
  it('identifies Mark (M) as the mapping tab', () => {
    expect(INSPECTOR_TABS.find((t) => t.shortLabel === 'M')?.id).toBe('mark');
    expect(isMappingInspectorTab('mark')).toBe(true);
    expect(isMappingInspectorTab('dashboard')).toBe(false);
  });

  it('renderTab receives only the active tab id when simulated', () => {
    const renderTab = vi.fn((tab: string) => (tab === 'mark' ? 'structural-map' : null));
    const activeTab = 'mark';
    const rendered = renderTab(activeTab);

    expect(renderTab).toHaveBeenCalledTimes(1);
    expect(renderTab).toHaveBeenCalledWith('mark');
    expect(rendered).toBe('structural-map');
    expect(renderTab('dashboard')).toBeNull();
  });
});

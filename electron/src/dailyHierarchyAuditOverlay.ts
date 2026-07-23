import './dailyHierarchyAuditOverlay.css';
import {
  buildDailyHierarchyAuditLayout,
  type DailyHierarchyAuditRowInput,
} from './dailyHierarchyAudit';

const OVERLAY_MARK = 'data-daily-hierarchy-audit-overlay';
const GLOBAL_CLEANUP_KEY = '__fxtmDailyHierarchyAuditOverlayCleanup';

type OverlayWindow = Window & typeof globalThis & {
  [GLOBAL_CLEANUP_KEY]?: () => void;
};

function hierarchyLayer(row: HTMLElement): string {
  const label = row.querySelector<HTMLElement>('.explorerTreeLine1');
  if (!label) return '';
  for (const className of Array.from(label.classList)) {
    if (className.startsWith('hierarchyLayer-')) {
      return className.slice('hierarchyLayer-'.length).toUpperCase();
    }
  }
  const text = String(label.textContent || '').trim().toUpperCase();
  return text.split(/\s+/)[0] || '';
}

function hierarchyDepth(row: HTMLElement): number {
  const raw = row.style.getPropertyValue('--tree-depth');
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed >= 0 ? Math.floor(parsed) : 0;
}

function clearRowDecoration(row: HTMLElement): void {
  row.classList.remove('dailyHierarchyAuditDecorated', 'dailyHierarchyAuditInvalid');
  delete row.dataset.dailyLinkStatus;
  delete row.dataset.dailyLinkReason;
  const rowMain = row.querySelector<HTMLElement>('.explorerTreeRowMain');
  if (rowMain) {
    delete rowMain.dataset.dailySequenceLabel;
    delete rowMain.dataset.dailyChildSummary;
  }
}

function decoratePanel(panel: Element): void {
  const rowElements = Array.from(panel.querySelectorAll<HTMLElement>('.explorerTreeScroll .explorerTreeRow'));
  if (!rowElements.length) return;

  const sourceRows: DailyHierarchyAuditRowInput[] = rowElements.map((row) => ({
    rangeId: String(row.dataset.rangeId || ''),
    layer: hierarchyLayer(row),
    depth: hierarchyDepth(row),
    orphan: row.classList.contains('orphan'),
  }));
  const layout = buildDailyHierarchyAuditLayout(sourceRows);
  const decorationByRangeId = new Map(layout.rows.map((item) => [item.rangeId, item]));
  const summaryByWeeklyId = new Map(layout.weeklySummaries.map((item) => [item.weeklyRangeId, item]));

  for (const row of rowElements) {
    clearRowDecoration(row);
    const rangeId = String(row.dataset.rangeId || '');
    const decoration = decorationByRangeId.get(rangeId);
    const rowMain = row.querySelector<HTMLElement>('.explorerTreeRowMain');
    if (!decoration || !rowMain) continue;

    row.classList.add('dailyHierarchyAuditDecorated');

    if (decoration.layer === 'DAILY') {
      rowMain.dataset.dailySequenceLabel = decoration.dailySequenceNumber === null
        ? 'R?'
        : `R${decoration.dailySequenceNumber}`;
      row.dataset.dailyLinkStatus = decoration.linkStatus || 'INVALID';
      row.dataset.dailyLinkReason = decoration.linkReason || '';
      if (decoration.linkStatus !== 'VALID') row.classList.add('dailyHierarchyAuditInvalid');
      continue;
    }

    if (decoration.layer === 'WEEKLY') {
      const summary = summaryByWeeklyId.get(rangeId);
      if (summary && summary.dailyCount > 0) {
        rowMain.dataset.dailyChildSummary = `${summary.dailyCount}D ✓`;
      }
    }
  }
}

function decorateAll(): void {
  document.querySelectorAll('.structuralExplorerPanel').forEach(decoratePanel);
}

export function startDailyHierarchyAuditOverlay(): () => void {
  let frame = 0;
  const schedule = () => {
    if (frame) return;
    frame = window.requestAnimationFrame(() => {
      frame = 0;
      decorateAll();
    });
  };

  schedule();
  const observer = new MutationObserver(schedule);
  observer.observe(document.body, { childList: true, subtree: true });

  return () => {
    observer.disconnect();
    if (frame) window.cancelAnimationFrame(frame);
    document.querySelectorAll(`[${OVERLAY_MARK}]`).forEach((node) => node.remove());
    document.querySelectorAll<HTMLElement>('.explorerTreeRow').forEach(clearRowDecoration);
  };
}

if (typeof window !== 'undefined' && typeof document !== 'undefined') {
  const overlayWindow = window as OverlayWindow;
  overlayWindow[GLOBAL_CLEANUP_KEY]?.();
  const start = () => {
    overlayWindow[GLOBAL_CLEANUP_KEY]?.();
    overlayWindow[GLOBAL_CLEANUP_KEY] = startDailyHierarchyAuditOverlay();
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
}

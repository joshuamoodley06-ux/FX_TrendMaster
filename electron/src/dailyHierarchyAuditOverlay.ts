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

function ensureBadge(
  row: HTMLElement,
  className: string,
  text: string,
  title: string,
  before: Element | null,
): HTMLElement {
  let badge = row.querySelector<HTMLElement>(`:scope > .${className}`);
  if (!badge) {
    badge = document.createElement('span');
    badge.className = className;
    badge.setAttribute(OVERLAY_MARK, 'true');
    if (before) row.insertBefore(badge, before);
    else row.appendChild(badge);
  }
  if (badge.textContent !== text) badge.textContent = text;
  if (badge.title !== title) badge.title = title;
  return badge;
}

function removeBadge(row: HTMLElement, className: string): void {
  row.querySelector<HTMLElement>(`:scope > .${className}`)?.remove();
}

function ensureLegend(panel: Element): void {
  const controls = panel.querySelector('.explorerTreeControls');
  if (!controls || panel.querySelector('.dailyHierarchyAuditLegend')) return;

  const legend = document.createElement('div');
  legend.className = 'dailyHierarchyAuditLegend';
  legend.setAttribute(OVERLAY_MARK, 'true');

  const heading = document.createElement('b');
  heading.textContent = 'Daily audit';
  const detail = document.createElement('span');
  detail.textContent = 'R# = order inside Weekly · ✓ linked · ! orphan/unlinked';
  legend.append(heading, detail);
  controls.insertAdjacentElement('afterend', legend);
}

function decoratePanel(panel: Element): void {
  ensureLegend(panel);
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
    const rangeId = String(row.dataset.rangeId || '');
    const decoration = decorationByRangeId.get(rangeId);
    const rowMain = row.querySelector('.explorerTreeRowMain');
    const actionMenu = row.querySelector('.explorerTreeActionMenu');
    row.classList.add('dailyHierarchyAuditDecorated');
    row.classList.remove('dailyHierarchyAuditInvalid');

    if (decoration?.layer === 'DAILY') {
      if (decoration.dailySequenceNumber !== null) {
        ensureBadge(
          row,
          'dailyHierarchySequenceBadge',
          `R${decoration.dailySequenceNumber}`,
          `Daily range ${decoration.dailySequenceNumber} inside Weekly parent ${decoration.parentWeeklyRangeId}.`,
          rowMain,
        );
      } else {
        ensureBadge(
          row,
          'dailyHierarchySequenceBadge',
          'R?',
          'Daily order unavailable because this range is not linked beneath a Weekly parent.',
          rowMain,
        );
      }

      const valid = decoration.linkStatus === 'VALID';
      const linkBadge = ensureBadge(
        row,
        'dailyHierarchyLinkBadge',
        valid ? '✓' : '!',
        `${valid ? 'VALID PARENT LINK' : 'INVALID PARENT LINK'} · ${decoration.linkReason || ''}`,
        actionMenu,
      );
      linkBadge.classList.toggle('valid', valid);
      linkBadge.classList.toggle('invalid', !valid);
      if (!valid) row.classList.add('dailyHierarchyAuditInvalid');
      removeBadge(row, 'dailyHierarchyWeeklySummary');
      continue;
    }

    removeBadge(row, 'dailyHierarchySequenceBadge');
    removeBadge(row, 'dailyHierarchyLinkBadge');

    if (decoration?.layer === 'WEEKLY') {
      const summary = summaryByWeeklyId.get(rangeId);
      if (summary && summary.dailyCount > 0) {
        ensureBadge(
          row,
          'dailyHierarchyWeeklySummary',
          `${summary.dailyCount}D ✓`,
          `${summary.dailyCount} visible Daily child range${summary.dailyCount === 1 ? '' : 's'} ordered beneath this Weekly parent.`,
          actionMenu,
        );
      } else {
        removeBadge(row, 'dailyHierarchyWeeklySummary');
      }
    } else {
      removeBadge(row, 'dailyHierarchyWeeklySummary');
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
    document.querySelectorAll('.dailyHierarchyAuditDecorated').forEach((node) => {
      node.classList.remove('dailyHierarchyAuditDecorated', 'dailyHierarchyAuditInvalid');
    });
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

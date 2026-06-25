import React, { useCallback, useEffect, useRef, useState } from 'react';

export type EventBrowserTreeNode = {
  range: any;
  depth: number;
  children: EventBrowserTreeNode[];
  childCountLabel?: string | null;
};

export type EventBrowserForest = {
  roots: EventBrowserTreeNode[];
  orphans: any[];
};

export type EventBrowserPanelProps = {
  forest: EventBrowserForest;
  resolveRowHighlight: (range: any) => { isActive: boolean; isParentContext: boolean };
  onRowClick: (range: any) => void;
  onClose: () => void;
  formatRowLabel: (range: any, directChildCount: number, childCountLabel?: string | null) => string;
  emptyMessage?: string;
  boundsRef?: React.RefObject<HTMLElement | null>;
};

type EventBrowserPanelPosition = {
  left: number;
  top: number;
};

function clampPanelPosition(
  left: number,
  top: number,
  panel: HTMLElement,
  bounds: HTMLElement,
): EventBrowserPanelPosition {
  const maxLeft = Math.max(0, bounds.clientWidth - panel.offsetWidth);
  const maxTop = Math.max(0, bounds.clientHeight - panel.offsetHeight);
  return {
    left: Math.max(0, Math.min(left, maxLeft)),
    top: Math.max(0, Math.min(top, maxTop)),
  };
}

function rangeIdOf(range: any): string {
  return String(range?.range_id || range?.id || '');
}

function EventBrowserTreeRows(props: {
  nodes: EventBrowserTreeNode[];
  collapsedIds: Set<string>;
  onToggleCollapsed: (id: string) => void;
  resolveRowHighlight: EventBrowserPanelProps['resolveRowHighlight'];
  onRowClick: EventBrowserPanelProps['onRowClick'];
  formatRowLabel: EventBrowserPanelProps['formatRowLabel'];
}): React.ReactElement[] {
  const {
    nodes,
    collapsedIds,
    onToggleCollapsed,
    resolveRowHighlight,
    onRowClick,
    formatRowLabel,
  } = props;

  return nodes.flatMap((node) => {
    const id = rangeIdOf(node.range);
    if (!id) return [];
    const hasChildren = node.children.length > 0;
    const collapsed = collapsedIds.has(id);
    const { isActive, isParentContext } = resolveRowHighlight(node.range);
    const label = formatRowLabel(node.range, node.children.length, node.childCountLabel);

    const row = (
      <div
        key={id}
        className={`eventBrowserPanelRow${isActive ? ' active' : ''}${isParentContext ? ' parentContext' : ''}`}
        style={{ ['--event-browser-depth' as string]: node.depth }}
      >
        {hasChildren ? (
          <button
            type="button"
            className="eventBrowserPanelExpandBtn"
            aria-label={collapsed ? 'Expand branch' : 'Collapse branch'}
            onClick={(event) => {
              event.stopPropagation();
              onToggleCollapsed(id);
            }}
          >
            {collapsed ? '+' : '−'}
          </button>
        ) : (
          <span className="eventBrowserPanelExpandSpacer" aria-hidden="true" />
        )}
        <button
          type="button"
          className="eventBrowserPanelRowBtn"
          title={label}
          onClick={() => onRowClick(node.range)}
        >
          <span className="eventBrowserPanelRowLabel">{label}</span>
        </button>
      </div>
    );

    if (collapsed) return [row];
    return [
      row,
      ...EventBrowserTreeRows({
        nodes: node.children,
        collapsedIds,
        onToggleCollapsed,
        resolveRowHighlight,
        onRowClick,
        formatRowLabel,
      }),
    ];
  });
}

export function EventBrowserPanel({
  forest,
  resolveRowHighlight,
  onRowClick,
  onClose,
  formatRowLabel,
  emptyMessage = 'No saved structural ranges for this case yet.',
  boundsRef,
}: EventBrowserPanelProps) {
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(() => new Set());
  const [position, setPosition] = useState<EventBrowserPanelPosition | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const toggleCollapsed = useCallback((id: string) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const resolveBoundsElement = useCallback((): HTMLElement | null => {
    const fromRef = boundsRef?.current;
    if (fromRef) return fromRef;
    const panel = panelRef.current;
    if (!panel) return null;
    const parent = panel.parentElement;
    return parent instanceof HTMLElement ? parent : null;
  }, [boundsRef]);

  const handleDragPointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();

    const handleEl = event.currentTarget;
    const panel = panelRef.current;
    const boundsEl = resolveBoundsElement();
    if (!panel || !boundsEl) return;

    handleEl.setPointerCapture(event.pointerId);

    const boundsRect = boundsEl.getBoundingClientRect();
    const panelRect = panel.getBoundingClientRect();
    const pointerOffsetX = event.clientX - panelRect.left;
    const pointerOffsetY = event.clientY - panelRect.top;

    const applyMove = (clientX: number, clientY: number) => {
      const nextBoundsRect = boundsEl.getBoundingClientRect();
      const left = clientX - nextBoundsRect.left - pointerOffsetX;
      const top = clientY - nextBoundsRect.top - pointerOffsetY;
      setPosition(clampPanelPosition(left, top, panel, boundsEl));
    };

    applyMove(event.clientX, event.clientY);

    const onPointerMove = (ev: PointerEvent) => {
      if (ev.pointerId !== event.pointerId) return;
      ev.preventDefault();
      ev.stopPropagation();
      applyMove(ev.clientX, ev.clientY);
    };

    const endDrag = (ev: PointerEvent) => {
      if (ev.pointerId !== event.pointerId) return;
      if (handleEl.hasPointerCapture(event.pointerId)) {
        handleEl.releasePointerCapture(event.pointerId);
      }
      handleEl.removeEventListener('pointermove', onPointerMove);
      handleEl.removeEventListener('pointerup', endDrag);
      handleEl.removeEventListener('pointercancel', endDrag);
    };

    handleEl.addEventListener('pointermove', onPointerMove);
    handleEl.addEventListener('pointerup', endDrag);
    handleEl.addEventListener('pointercancel', endDrag);
  }, [resolveBoundsElement]);

  useEffect(() => {
    if (position === null) return;
    const boundsEl = resolveBoundsElement();
    const panel = panelRef.current;
    if (!boundsEl || !panel) return;

    const reclamp = () => {
      setPosition((prev) => {
        if (!prev) return prev;
        return clampPanelPosition(prev.left, prev.top, panel, boundsEl);
      });
    };

    const observer = new ResizeObserver(reclamp);
    observer.observe(boundsEl);
    observer.observe(panel);
    return () => observer.disconnect();
  }, [position === null, resolveBoundsElement]);

  const hasRows = forest.roots.length > 0 || forest.orphans.length > 0;
  const panelStyle: React.CSSProperties | undefined = position
    ? { top: position.top, left: position.left, right: 'auto' }
    : undefined;

  return (
    <div
      ref={panelRef}
      className={`eventBrowserPanel${position ? ' eventBrowserPanelPositioned' : ''}`}
      style={panelStyle}
      aria-label="Event Browser"
    >
      <div className="eventBrowserPanelHeader">
        <div
          className="eventBrowserPanelDragHandle"
          onPointerDown={handleDragPointerDown}
          aria-label="Drag Event Browser"
        >
          <span className="eventBrowserPanelTitle">Event Browser</span>
        </div>
        <button
          type="button"
          className="eventBrowserPanelCloseBtn"
          onClick={onClose}
          onPointerDown={(event) => event.stopPropagation()}
          aria-label="Close Event Browser"
        >
          ×
        </button>
      </div>
      <div className="eventBrowserPanelBody">
        {!hasRows && (
          <div className="eventBrowserPanelEmpty">{emptyMessage}</div>
        )}
        {EventBrowserTreeRows({
          nodes: forest.roots,
          collapsedIds,
          onToggleCollapsed: toggleCollapsed,
          resolveRowHighlight,
          onRowClick,
          formatRowLabel,
        }).map((row) => row)}
        {forest.orphans.length > 0 && (
          <>
            <div className="eventBrowserPanelSectionLabel">Unlinked / Orphans</div>
            {forest.orphans.map((range) => {
              const id = rangeIdOf(range);
              if (!id) return null;
              const { isActive } = resolveRowHighlight(range);
              const label = formatRowLabel(range, 0);
              return (
                <div key={`orphan-${id}`} className={`eventBrowserPanelRow orphan${isActive ? ' active' : ''}`}>
                  <span className="eventBrowserPanelExpandSpacer" aria-hidden="true" />
                  <button
                    type="button"
                    className="eventBrowserPanelRowBtn"
                    title={label}
                    onClick={() => onRowClick(range)}
                  >
                    <span className="eventBrowserPanelRowLabel">{label}</span>
                  </button>
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}

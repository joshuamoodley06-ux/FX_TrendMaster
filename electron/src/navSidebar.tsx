import React, { useEffect, useRef, useState } from 'react';
import { BookOpen, Database, Map as MapIcon, RefreshCw, Settings } from 'lucide-react';
import brandLogo from '../assets/logo.png';
import {
  type AppPage,
  bootstrapAppPage,
  isAdminPage,
  navigateToPage,
  readPageFromLocation,
} from './appNavigation';

type NavIconProps = {
  label: string;
  page: AppPage;
  active: boolean;
  onNavigate: (page: AppPage) => void;
  children: React.ReactNode;
};

function NavIcon({ label, page, active, onNavigate, children }: NavIconProps) {
  return (
    <button
      type="button"
      className={`navIconBtn${active ? ' active' : ''}`}
      title={label}
      aria-label={label}
      aria-current={active ? 'page' : undefined}
      onClick={() => onNavigate(page)}
    >
      {children}
    </button>
  );
}

const FLYOUT_ITEMS: { page: AppPage; label: string }[] = [
  { page: 'historical', label: 'Historical Builder' },
  { page: 'settings', label: 'Display Settings' },
  { page: 'sql', label: 'SQL / Backend' },
  { page: 'brain', label: 'Lifecycle Catch-Up' },
  { page: 'ideas', label: 'Trade Ideas' },
];

type SettingsFlyoutProps = {
  page: AppPage;
  onNavigate: (page: AppPage) => void;
};

function NavSettingsFlyout({ page, onNavigate }: SettingsFlyoutProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const settingsActive = isAdminPage(page);

  return (
    <div className="navSettingsFlyout" ref={rootRef}>
      {open && (
        <div className="navFlyoutMenu" role="menu" aria-label="Admin tools">
          {FLYOUT_ITEMS.map((item) => (
            <button
              key={item.page}
              type="button"
              role="menuitem"
              className={page === item.page ? 'active' : ''}
              onClick={() => {
                onNavigate(item.page);
                setOpen(false);
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
      <button
        type="button"
        className={`navIconBtn navSettingsBtn${settingsActive ? ' active' : ''}${open ? ' open' : ''}`}
        title="Settings"
        aria-label="Settings"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((v) => !v)}
      >
        <Settings size={20} strokeWidth={1.75} />
      </button>
    </div>
  );
}

type NavSidebarProps = {
  page: AppPage;
  apiOnline: boolean | null;
  onNavigate: (page: AppPage) => void;
  onRefresh?: () => void;
};

export function NavSidebar({ page, apiOnline, onNavigate, onRefresh }: NavSidebarProps) {
  return (
    <aside className="navLibrary sidebar navRail" aria-label="Navigation">
      <div className="navRailBrand" title="FX TrendMaster">
        <img className="brandLogo" src={brandLogo} alt="" />
        <span className="navRailBrandText">TrendMaster</span>
      </div>

      <nav className="navRailPrimary" aria-label="Primary">
        <NavIcon label="Map Studio" page="mapstudio" active={page === 'mapstudio'} onNavigate={onNavigate}>
          <MapIcon size={20} strokeWidth={1.75} />
        </NavIcon>
        <NavIcon label="Journal" page="journal" active={page === 'journal'} onNavigate={onNavigate}>
          <BookOpen size={20} strokeWidth={1.75} />
        </NavIcon>
        <NavIcon label="Data" page="data" active={page === 'data'} onNavigate={onNavigate}>
          <Database size={20} strokeWidth={1.75} />
        </NavIcon>
      </nav>

      <div className="navRailFooter">
        <NavSettingsFlyout page={page} onNavigate={onNavigate} />
        {onRefresh && (
          <button
            type="button"
            className="navIconBtn navRefreshBtn"
            title="Refresh VPS snapshot (manual)"
            aria-label="Refresh VPS snapshot"
            onClick={onRefresh}
          >
            <RefreshCw size={18} strokeWidth={1.75} />
          </button>
        )}
        <div className="navRailStatus" title={apiOnline ? 'VPS Online' : apiOnline === false ? 'VPS Offline' : 'Not synced — use Refresh'}>
          <span className={`dot ${apiOnline ? 'online' : apiOnline === false ? 'offline' : ''}`} />
        </div>
      </div>
    </aside>
  );
}

export function useAppPageNavigation(initialPage?: AppPage) {
  const [page, setPageState] = useState<AppPage>(() => initialPage ?? bootstrapAppPage());

  useEffect(() => {
    const sync = () => {
      const next = readPageFromLocation();
      if (next) setPageState(next);
    };
    window.addEventListener('popstate', sync);
    window.addEventListener('hashchange', sync);
    return () => {
      window.removeEventListener('popstate', sync);
      window.removeEventListener('hashchange', sync);
    };
  }, []);

  const setPage = (next: AppPage) => {
    setPageState(next);
    navigateToPage(next);
  };

  return { page, setPage };
}

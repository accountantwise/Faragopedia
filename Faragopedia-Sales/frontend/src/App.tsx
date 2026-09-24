import React, { useState, useRef, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import SetupWizard from './components/SetupWizard';
import WikiView from './components/WikiView';
import SourcesView from './components/SourcesView';
import ArchiveView from './components/ArchiveView';
import LintView from './components/LintView';
import LinkView from './components/LinkView';
import ChatPanel from './components/ChatPanel';
import { Loader2, Menu, X } from 'lucide-react';
import { API_BASE } from './config';
import SettingsDrawer from './components/SettingsDrawer';
import { useOperationToasts } from './OperationToastContext';
import OperationToastStack from './components/OperationToastStack';

const App: React.FC = () => {
  const [setupState, setSetupState] = useState<'loading' | 'required' | 'ready'>('loading');
  const [wikiName, setWikiName] = useState('Wiki');
  const [reconfigureMode, setReconfigureMode] = useState(false);
  const [existingFolders, setExistingFolders] = useState<string[]>([]);
  const [currentView, setCurrentView] = useState('Wiki');
  const [pendingChatPage, setPendingChatPage] = useState<string | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sourcesMetadata, setSourcesMetadata] = useState<Record<string, { ingested: boolean; ingested_at: string | null; tags: string[] }>>({});
  const prevMetadataRef = useRef<Record<string, { ingested: boolean; ingested_at: string | null; tags: string[] }>>({});
  const { completeIngest, completeCrawl } = useOperationToasts();
  const prevFilenamesRef = useRef<Set<string>>(new Set());
  const [pagesMetadata, setPagesMetadata] = useState<Record<string, { read: boolean; read_at: string | null }>>({});

  const handleMarkPageRead = useCallback(async (path: string) => {
    setPagesMetadata(prev => ({
      ...prev,
      [path]: { read: true, read_at: new Date().toISOString() },
    }));
    fetch(`${API_BASE}/pages/mark-read`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    }).catch(() => {});
  }, []);

  const [workspaces, setWorkspaces] = useState<{ id: string; name: string; archived?: boolean }[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState('');
  const [previousActiveWorkspaceId, setPreviousActiveWorkspaceId] = useState('');

  const [theme, setTheme] = useState<'light' | 'dark' | 'system'>(() => {
    try { return (localStorage.getItem('faragopedia-theme') as 'light' | 'dark' | 'system') ?? 'system'; } catch (_) { return 'system'; }
  });
  const [settingsOpen, setSettingsOpen] = useState(false);

  const fetchWorkspaces = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/workspaces`);
      if (!res.ok) return;
      const data = await res.json();
      setWorkspaces(data.workspaces ?? []);
      setActiveWorkspaceId(data.active_workspace_id ?? '');
    } catch (_) {}
  }, []);

  // Setup status check — must be first useEffect
  useEffect(() => {
    fetch(`${API_BASE}/setup/status`)
      .then(r => r.json())
      .then(data => {
        if (data.setup_required) {
          setSetupState('required');
        } else {
          setWikiName(data.wiki_name || 'Wiki');
          setSetupState('ready');
          fetchWorkspaces();
        }
      })
      .catch(() => setSetupState('required'));
  }, [fetchWorkspaces]);

  useEffect(() => {
    try { localStorage.setItem('faragopedia-theme', theme); } catch (_) {}
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else if (theme === 'light') {
      root.classList.remove('dark');
    } else {
      const mq = window.matchMedia('(prefers-color-scheme: dark)');
      root.classList.toggle('dark', mq.matches);
      const handler = (e: MediaQueryListEvent) => root.classList.toggle('dark', e.matches);
      mq.addEventListener('change', handler);
      return () => mq.removeEventListener('change', handler);
    }
  }, [theme]);

  useEffect(() => {
    const fetchMetadata = async () => {
      try {
        const res = await fetch(`${API_BASE}/sources/metadata`);
        if (!res.ok) return;
        const data: Record<string, { ingested: boolean; ingested_at: string | null; tags: string[] }> = await res.json();

        const prev = prevMetadataRef.current;
        const prevFilenames = prevFilenamesRef.current;
        const currentFilenames = new Set(Object.keys(data));

        // Detect ingest completions
        Object.entries(data).forEach(([filename, meta]) => {
          if (meta.ingested && prev[filename] && !prev[filename].ingested) {
            completeIngest(filename);
          }
        });

        // Detect crawl completions — completeCrawl is a no-op when no crawl is in-flight
        const newFilenames = Array.from(currentFilenames).filter(f => !prevFilenames.has(f));
        if (newFilenames.length > 0) {
          completeCrawl(newFilenames);
        }

        prevMetadataRef.current = data;
        prevFilenamesRef.current = currentFilenames;
        setSourcesMetadata(data);
      } catch (err) {
        console.error('Failed to fetch metadata', err);
      }

      // Also refresh page read/unread state
      try {
        const pagesRes = await fetch(`${API_BASE}/pages/metadata`);
        if (pagesRes.ok) {
          const pagesData: Record<string, { read: boolean; read_at: string | null }> = await pagesRes.json();
          setPagesMetadata(prev => {
            const merged = { ...prev };
            for (const [k, v] of Object.entries(pagesData)) {
              if (merged[k]?.read !== true) merged[k] = v;
            }
            return merged;
          });
        }
      } catch {
        // non-fatal
      }
    };

    fetchMetadata();
    const interval = setInterval(fetchMetadata, 5000);
    return () => clearInterval(interval);
  }, [completeIngest, completeCrawl]);

  const handleSetupComplete = async () => {
    const res = await fetch(`${API_BASE}/setup/config`);
    if (res.ok) {
      const data = await res.json();
      setWikiName(data.wiki_name);
    }
    setReconfigureMode(false);
    setPreviousActiveWorkspaceId('');
    setSetupState('ready');
  };

  const handleReconfigure = async () => {
    // We use /folders (GET) instead of /clear (POST) to avoid deleting
    // the wiki_config.json until the user actually completes the wizard.
    const res = await fetch(`${API_BASE}/setup/folders`);
    if (res.ok) {
      const data = await res.json();
      setExistingFolders(data.existing_folders);
    }
    setReconfigureMode(true);
    setSetupState('required');
  };

  const handleSetupCancel = () => {
    setReconfigureMode(false);
    setSetupState('ready');
  };

  const handleSwitchWorkspace = async (id: string) => {
    const res = await fetch(`${API_BASE}/workspaces/${id}/switch`, { method: 'POST' });
    if (!res.ok) return;
    const data = await res.json();
    setActiveWorkspaceId(id);
    setCurrentView('Wiki');
    setSourcesMetadata({});
    if (data.setup_required) {
      setReconfigureMode(false);
      setExistingFolders([]);
      setSetupState('required');
    } else {
      setWikiName(data.wiki_name || 'Wiki');
      setSetupState('ready');
    }
    fetchWorkspaces();
  };

  const handleNewWorkspace = async () => {
    setPreviousActiveWorkspaceId(activeWorkspaceId);
    const res = await fetch(`${API_BASE}/workspaces`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'New Workspace' }),
    });
    if (!res.ok) return;
    const data = await res.json();
    setActiveWorkspaceId(data.id);
    setCurrentView('Wiki');
    setSourcesMetadata({});
    setSetupState('required');
    setReconfigureMode(false);
    setExistingFolders([]);
    fetchWorkspaces();
  };

  const handleArchiveWorkspace = async (id: string) => {
    await fetch(`${API_BASE}/workspaces/${id}/archive`, { method: 'POST' });
    fetchWorkspaces();
  };

  const handleUnarchiveWorkspace = async (id: string) => {
    await fetch(`${API_BASE}/workspaces/${id}/unarchive`, { method: 'POST' });
    fetchWorkspaces();
  };

  const handleDeleteWorkspace = async (id: string) => {
    const res = await fetch(`${API_BASE}/workspaces/${id}`, { method: 'DELETE' });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail ?? 'Delete failed');
    }
    fetchWorkspaces();
  };

  const handleRenameWorkspace = async (id: string, name: string) => {
    const res = await fetch(`${API_BASE}/workspaces/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail ?? 'Rename failed');
    }
    fetchWorkspaces();
  };

  const handleDuplicateWorkspace = async (id: string, name: string, mode: 'full' | 'template') => {
    const res = await fetch(`${API_BASE}/workspaces/${id}/duplicate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, mode }),
    });
    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail ?? 'Duplicate failed');
    }
    const data = await res.json();
    setActiveWorkspaceId(data.id);
    setCurrentView('Wiki');
    setSourcesMetadata({});
    if (data.setup_required) {
      setReconfigureMode(false);
      setExistingFolders([]);
      setSetupState('required');
    } else {
      setSetupState('ready');
    }
    fetchWorkspaces();
  };

  const renderContent = () => {
    switch (currentView) {
      case 'Wiki':
        return (
          <WikiView
            key={activeWorkspaceId}
            pagesMetadata={pagesMetadata}
            onMarkPageRead={handleMarkPageRead}
            initialPagePath={pendingChatPage}
            onInitialPageConsumed={() => setPendingChatPage(null)}
          />
        );
      case 'Sources':
        return <SourcesView key={activeWorkspaceId} sourcesMetadata={sourcesMetadata} />;
      case 'Chat':
        return (
          <div className="p-12 max-w-4xl mx-auto h-full flex flex-col">
            <h1 className="text-4xl font-extrabold text-gray-900 dark:text-gray-100 mb-6 tracking-tight">AI Assistant</h1>
            <p className="text-xl text-gray-500 dark:text-gray-400 mb-8 leading-relaxed">
              Ask questions about your data. The AI synthesises answers from wiki pages and cites sources.
            </p>
            <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 flex-grow flex flex-col overflow-hidden mb-8">
              <ChatPanel
                key={activeWorkspaceId}
                showHeader={false}
                onLinkClick={(path) => {
                  setPendingChatPage(path);
                  setCurrentView('Wiki');
                }}
              />
            </div>
          </div>
        );
      case 'Archive':
        return <ArchiveView key={activeWorkspaceId} />;
      case 'Lint':
        return <LintView key={activeWorkspaceId} />;
      case 'Links':
        return <LinkView key={activeWorkspaceId} />;
      default:
        return <div className="p-8">Select a view</div>;
    }
  };

  if (setupState === 'loading') {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (setupState === 'required') {
    return (
      <SetupWizard
        onComplete={handleSetupComplete}
        onCancel={
          reconfigureMode
            ? handleSetupCancel
            : previousActiveWorkspaceId
              ? () => {
                  handleSwitchWorkspace(previousActiveWorkspaceId);
                  setPreviousActiveWorkspaceId('');
                }
              : undefined
        }
        reconfigureMode={reconfigureMode}
        existingFolders={existingFolders}
      />
    );
  }

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-950 font-sans antialiased text-gray-900 dark:text-gray-100 overflow-hidden">
      {/* Mobile overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar container */}
      <div
        className={`fixed inset-y-0 left-0 z-50 flex-shrink-0 h-screen bg-gray-800 overflow-hidden transition-all duration-300 ease-in-out transform ${
          mobileMenuOpen ? 'translate-x-0 w-64' : '-translate-x-full w-64'
        } md:relative md:translate-x-0 ${sidebarOpen ? 'md:w-64' : 'md:w-0'}`}
      >
        <div className="w-64 h-full relative">
          <Sidebar
            currentView={currentView}
            onViewChange={(v) => { setCurrentView(v); setMobileMenuOpen(false); }}
            wikiName={wikiName}
            onOpenSettings={() => setSettingsOpen(true)}
            workspaces={workspaces}
            activeWorkspaceId={activeWorkspaceId}
            onSwitchWorkspace={handleSwitchWorkspace}
            onNewWorkspace={handleNewWorkspace}
            onArchiveWorkspace={handleArchiveWorkspace}
            onUnarchiveWorkspace={handleUnarchiveWorkspace}
            onDuplicateWorkspace={handleDuplicateWorkspace}
            onDeleteWorkspace={handleDeleteWorkspace}
            onRenameWorkspace={handleRenameWorkspace}
          />
          <button
            className="md:hidden absolute top-4 right-4 text-gray-400 hover:text-white p-2 rounded-lg bg-gray-800/80"
            onClick={() => setMobileMenuOpen(false)}
          >
            <X className="w-6 h-6" />
          </button>
        </div>
      </div>

      <main className="flex-grow flex flex-col overflow-hidden relative w-full">
        <div className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-4 py-4 flex items-center shrink-0 z-30 relative shadow-sm">
          <button
            onClick={() => {
              if (window.innerWidth < 768) setMobileMenuOpen(true);
              else setSidebarOpen(prev => !prev);
            }}
            className="p-2 -ml-2 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg flex items-center justify-center transition-colors focus:ring-2 focus:ring-blue-500 outline-none"
            aria-label="Toggle Navigation"
          >
            <Menu className="w-6 h-6" />
          </button>
          {!sidebarOpen && (
            <span className="hidden md:ml-4 font-bold text-gray-800 dark:text-gray-200 md:inline-block">{wikiName}</span>
          )}
          <span className="ml-4 font-bold text-gray-800 dark:text-gray-200 md:hidden">{wikiName}</span>
        </div>
        <div className="flex-grow overflow-hidden relative h-full">
          {renderContent()}
        </div>
        <OperationToastStack />
      </main>
      <SettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        theme={theme}
        onThemeChange={setTheme}
        onReconfigure={() => { setSettingsOpen(false); handleReconfigure(); }}
      />
    </div>
  );
};

export default App;

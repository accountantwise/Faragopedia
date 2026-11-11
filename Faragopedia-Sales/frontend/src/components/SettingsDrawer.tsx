import React, { useEffect, useState } from 'react';
import { X, RefreshCw, Download, Settings, Upload } from 'lucide-react';
import { API_BASE } from '../config';

interface SettingsDrawerProps {
  open: boolean;
  onClose: () => void;
  theme: 'light' | 'dark' | 'system';
  onThemeChange: (t: 'light' | 'dark' | 'system') => void;
  onReconfigure: () => void;
}

const THEMES: { value: 'light' | 'dark' | 'system'; label: string }[] = [
  { value: 'light', label: '☀ Light' },
  { value: 'system', label: '◑ System' },
  { value: 'dark', label: '● Dark' },
];

const SettingsDrawer: React.FC<SettingsDrawerProps> = ({
  open,
  onClose,
  theme,
  onThemeChange,
  onReconfigure,
}) => {
  const [wikiName, setWikiName] = useState('');
  const [importLoading, setImportLoading] = useState(false);
  const [importError, setImportError] = useState('');

  useEffect(() => {
    if (open && !wikiName) {
      fetch(`${API_BASE}/setup/config`)
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (data?.wiki_name) setWikiName(data.wiki_name); })
        .catch(() => {});
    }
  }, [open, wikiName]);

  const handleExportFull = () => {
    window.open(`${API_BASE}/export/bundle/full`, '_blank');
  };

  const handleExportTemplate = () => {
    window.open(`${API_BASE}/export/bundle/template`, '_blank');
  };

  const handleImport = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.zip';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      setImportLoading(true);
      setImportError('');
      const form = new FormData();
      form.append('file', file);
      try {
        const r = await fetch(`${API_BASE}/export/import`, { method: 'POST', body: form });
        if (!r.ok) {
          const err = await r.json().catch(() => ({ detail: 'Import failed' }));
          setImportError(err.detail || 'Import failed');
          return;
        }
        const data = await r.json();
        if (data.type === 'template') {
          sessionStorage.setItem('templateImport', JSON.stringify({
            wiki_name: data.wiki_name,
            org_name: data.org_name,
            org_description: data.org_description,
            entity_types: data.entity_types,
          }));
        }
        window.location.reload();
      } catch {
        setImportError('Import failed. Please try again.');
      } finally {
        setImportLoading(false);
      }
    };
    input.click();
  };

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/40 z-40"
          onClick={onClose}
        />
      )}

      {/* Drawer */}
      <div
        className="fixed inset-y-0 right-0 z-50 w-80 bg-white dark:bg-gray-900 shadow-2xl flex flex-col"
        style={{
          transform: open ? 'translateX(0)' : 'translateX(100%)',
          transition: 'transform 0.3s ease-in-out',
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2 font-semibold text-gray-900 dark:text-gray-100">
            <Settings className="w-4 h-4" />
            Settings
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">

          {/* Appearance */}
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-gray-400 dark:text-gray-500 mb-3">
              Appearance
            </p>
            <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-4">
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">Theme</p>
              <div className="flex bg-gray-200 dark:bg-gray-700 rounded-lg p-1 gap-1">
                {THEMES.map(t => (
                  <button
                    key={t.value}
                    onClick={() => onThemeChange(t.value)}
                    className={`flex-1 py-1.5 rounded-md text-xs font-medium transition-all ${
                      theme === t.value
                        ? 'bg-blue-600 text-white shadow'
                        : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Wiki */}
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-gray-400 dark:text-gray-500 mb-3">
              Wiki
            </p>
            <button
              onClick={onReconfigure}
              className="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-sm"
            >
              <RefreshCw className="w-4 h-4" />
              Reconfigure Wiki
            </button>
          </div>

          {/* Export */}
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-gray-400 dark:text-gray-500 mb-3">
              Export
            </p>
            <div className="space-y-2">
              <button
                onClick={handleExportFull}
                className="w-full flex items-start gap-3 px-3 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-left transition-colors"
              >
                <Download size={16} className="mt-0.5 shrink-0 text-gray-500 dark:text-gray-400" />
                <div>
                  <div className="text-sm font-medium text-gray-700 dark:text-gray-300">Export Full</div>
                  <div className="text-xs text-gray-500 dark:text-gray-500">All pages, sources, archive &amp; snapshots</div>
                </div>
              </button>
              <button
                onClick={handleExportTemplate}
                className="w-full flex items-start gap-3 px-3 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-left transition-colors"
              >
                <Download size={16} className="mt-0.5 shrink-0 text-gray-500 dark:text-gray-400" />
                <div>
                  <div className="text-sm font-medium text-gray-700 dark:text-gray-300">Export Template</div>
                  <div className="text-xs text-gray-500 dark:text-gray-500">Schema &amp; folder structure only — no content</div>
                </div>
              </button>
            </div>
          </div>

          {/* Import */}
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-gray-400 dark:text-gray-500 mb-3">
              Import
            </p>
            <div className="space-y-2">
              <button
                onClick={handleImport}
                disabled={importLoading}
                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-left transition-colors disabled:opacity-50"
              >
                <Upload size={16} className="shrink-0 text-gray-500 dark:text-gray-400" />
                <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  {importLoading ? 'Importing…' : 'Import Bundle'}
                </div>
              </button>
              {importError && (
                <p className="text-xs text-red-500 dark:text-red-400 px-1">{importError}</p>
              )}
            </div>
          </div>

        </div>

        {/* Footer */}
        {wikiName && (
          <div className="px-5 py-3 border-t border-gray-100 dark:border-gray-800">
            <p className="text-xs text-gray-400 dark:text-gray-600">{wikiName}</p>
          </div>
        )}
      </div>
    </>
  );
};

export default SettingsDrawer;

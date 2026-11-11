import React, { useEffect, useState } from 'react';
import { Loader2, Plus, Trash2, ChevronDown, ChevronRight, X } from 'lucide-react';
import { API_BASE } from '../config';

// ── Types ────────────────────────────────────────────────────────────────────

interface EntityField {
  name: string;
  type: 'string' | 'date' | 'integer' | 'enum' | 'list';
  required?: boolean;
  values?: string[];
  default?: string;
  description?: string;
}

interface EntityType {
  folder_name: string;
  display_name: string;
  description: string;
  singular: string;
  fields: EntityField[];
  sections: string[];
}

interface SetupWizardProps {
  onComplete: () => void;
  onCancel?: () => void;
  reconfigureMode?: boolean;
  existingFolders?: string[];
}

// ── Preset fallback schemas ───────────────────────────────────────────────────

const PRESETS: Record<string, EntityType[]> = {
  'Creative Production': [
    { folder_name: 'clients', display_name: 'Clients', description: 'Client organisations', singular: 'client', fields: [{ name: 'name', type: 'string', required: true }, { name: 'status', type: 'enum', values: ['active', 'inactive'] }], sections: ['Overview', 'Notes'] },
    { folder_name: 'contacts', display_name: 'Contacts', description: 'Individual people', singular: 'contact', fields: [{ name: 'name', type: 'string', required: true }, { name: 'role', type: 'string' }], sections: ['Bio', 'Notes'] },
    { folder_name: 'photographers', display_name: 'Photographers', description: 'Photographer roster', singular: 'photographer', fields: [{ name: 'name', type: 'string', required: true }], sections: ['Bio', 'Style Notes'] },
    { folder_name: 'productions', display_name: 'Productions', description: 'Shoots and projects', singular: 'production', fields: [{ name: 'name', type: 'string', required: true }, { name: 'date', type: 'date' }], sections: ['Brief', 'Team', 'Notes'] },
    { folder_name: 'prospects', display_name: 'Prospects', description: 'Pipeline prospects', singular: 'prospect', fields: [{ name: 'name', type: 'string', required: true }], sections: ['Overview', 'Outreach'] },
  ],
  'CRM': [
    { folder_name: 'organisations', display_name: 'Organisations', description: 'Companies and orgs', singular: 'organisation', fields: [{ name: 'name', type: 'string', required: true }], sections: ['Overview', 'Contacts', 'Notes'] },
    { folder_name: 'contacts', display_name: 'Contacts', description: 'Individual contacts', singular: 'contact', fields: [{ name: 'name', type: 'string', required: true }, { name: 'email', type: 'string' }], sections: ['Bio', 'Notes'] },
    { folder_name: 'deals', display_name: 'Deals', description: 'Sales opportunities', singular: 'deal', fields: [{ name: 'name', type: 'string', required: true }, { name: 'stage', type: 'enum', values: ['prospect', 'qualified', 'closed-won', 'closed-lost'] }], sections: ['Overview', 'Notes'] },
    { folder_name: 'notes', display_name: 'Notes', description: 'Meeting and call notes', singular: 'note', fields: [{ name: 'name', type: 'string', required: true }, { name: 'date', type: 'date' }], sections: ['Content'] },
  ],
  'Research': [
    { folder_name: 'topics', display_name: 'Topics', description: 'Research topics', singular: 'topic', fields: [{ name: 'name', type: 'string', required: true }], sections: ['Overview', 'Notes'] },
    { folder_name: 'papers', display_name: 'Papers', description: 'Academic papers', singular: 'paper', fields: [{ name: 'name', type: 'string', required: true }, { name: 'year', type: 'integer' }], sections: ['Abstract', 'Notes'] },
    { folder_name: 'authors', display_name: 'Authors', description: 'Researchers and authors', singular: 'author', fields: [{ name: 'name', type: 'string', required: true }], sections: ['Bio', 'Works'] },
    { folder_name: 'notes', display_name: 'Notes', description: 'Research notes', singular: 'note', fields: [{ name: 'name', type: 'string', required: true }], sections: ['Content'] },
  ],
  'Blank': [],
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function slugify(str: string): string {
  return str.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '').replace(/-+/g, '-');
}

function blankField(): EntityField {
  return { name: '', type: 'string' };
}

function blankEntityType(): EntityType {
  return {
    folder_name: '',
    display_name: '',
    description: '',
    singular: '',
    fields: [{ name: 'name', type: 'string', required: true }],
    sections: [],
  };
}

// ── Field editor sub-component ────────────────────────────────────────────────

const FieldEditor: React.FC<{
  field: EntityField;
  onChange: (f: EntityField) => void;
  onDelete: () => void;
}> = ({ field, onChange, onDelete }) => {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg mb-1">
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800"
        onClick={() => setExpanded(e => !e)}
      >
        {expanded ? <ChevronDown className="w-3 h-3 text-gray-400" /> : <ChevronRight className="w-3 h-3 text-gray-400" />}
        <span className="text-sm flex-1 font-mono text-gray-900 dark:text-gray-100">{field.name || <span className="text-gray-400 italic">unnamed</span>}</span>
        <span className="text-xs px-2 py-0.5 rounded bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400">{field.type}</span>
        {field.required && <span className="text-xs text-green-600 dark:text-green-400">required</span>}
        <button onClick={(e) => { e.stopPropagation(); onDelete(); }} className="text-red-400 hover:text-red-600 ml-1"><Trash2 className="w-3 h-3" /></button>
      </div>
      {expanded && (
        <div className="px-3 pb-3 pt-1 grid grid-cols-2 gap-2 border-t border-gray-100">
          <div>
            <label className="text-xs text-gray-500 block mb-1">Name</label>
            <input className="w-full border dark:border-gray-700 rounded px-2 py-1 text-sm dark:bg-gray-800 dark:text-white" value={field.name} onChange={e => onChange({ ...field, name: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Type</label>
            <select className="w-full border dark:border-gray-700 rounded px-2 py-1 text-sm dark:bg-gray-800 dark:text-white" value={field.type} onChange={e => onChange({ ...field, type: e.target.value as EntityField['type'] })}>
              {(['string', 'date', 'integer', 'enum', 'list'] as const).map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          {field.type === 'enum' && (
            <div className="col-span-2">
              <label className="text-xs text-gray-500 block mb-1">Enum values (comma-separated)</label>
              <input className="w-full border dark:border-gray-700 rounded px-2 py-1 text-sm dark:bg-gray-800 dark:text-white" value={(field.values || []).join(', ')} onChange={e => onChange({ ...field, values: e.target.value.split(',').map(v => v.trim()).filter(Boolean) })} />
            </div>
          )}
          <div className="col-span-2 flex items-center gap-2">
            <input type="checkbox" id={`req-${field.name}`} checked={!!field.required} onChange={e => onChange({ ...field, required: e.target.checked })} />
            <label htmlFor={`req-${field.name}`} className="text-xs text-gray-500">Required</label>
          </div>
          <div className="col-span-2">
            <label className="text-xs text-gray-500 block mb-1">Description (optional)</label>
            <input className="w-full border dark:border-gray-700 rounded px-2 py-1 text-sm dark:bg-gray-800 dark:text-white" value={field.description || ''} onChange={e => onChange({ ...field, description: e.target.value })} />
          </div>
        </div>
      )}
    </div>
  );
};

// ── Entity card sub-component ─────────────────────────────────────────────────

const EntityCard: React.FC<{
  et: EntityType;
  badge?: string;
  onChange: (et: EntityType) => void;
  onDelete: () => void;
}> = ({ et, badge, onChange, onDelete }) => {
  const [expanded, setExpanded] = useState(true);
  const [newSection, setNewSection] = useState('');

  return (
    <div className="border border-gray-200 dark:border-gray-800 rounded-xl bg-white dark:bg-gray-900 shadow-sm mb-3">
      <div className="flex items-center gap-3 px-4 py-3 cursor-pointer" onClick={() => setExpanded(e => !e)}>
        {expanded ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
        <div className="flex-1">
          <div className="text-xs text-gray-400 font-mono">folder: {et.folder_name || '—'}</div>
          <div className="font-semibold text-gray-800 dark:text-gray-100">{et.display_name || <span className="text-gray-400 italic">Unnamed</span>}</div>
        </div>
        {badge && <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400">{badge}</span>}
        {!expanded && <span className="text-xs text-gray-400">{et.fields.length} fields · {et.sections.length} sections</span>}
        <button onClick={(e) => { e.stopPropagation(); onDelete(); }} className="text-red-400 hover:text-red-600"><Trash2 className="w-4 h-4" /></button>
      </div>

      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-100 dark:border-gray-800 pt-3 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500 block mb-1">Display Name</label>
              <input
                className="w-full border dark:border-gray-700 rounded px-2 py-1.5 text-sm dark:bg-gray-800 dark:text-white"
                value={et.display_name}
                onChange={e => {
                  const display_name = e.target.value;
                  onChange({ ...et, display_name, folder_name: slugify(display_name), singular: slugify(display_name).replace(/-?s$/, '') });
                }}
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Folder slug (editable)</label>
              <input className="w-full border dark:border-gray-700 rounded px-2 py-1.5 text-sm font-mono dark:bg-gray-800 dark:text-white" value={et.folder_name} onChange={e => onChange({ ...et, folder_name: e.target.value })} />
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Description</label>
            <textarea className="w-full border dark:border-gray-700 rounded px-2 py-1.5 text-sm resize-none dark:bg-gray-800 dark:text-white" rows={2} value={et.description} onChange={e => onChange({ ...et, description: e.target.value })} />
          </div>

          <div>
            <div className="text-xs text-gray-500 mb-2 uppercase tracking-wide">Fields</div>
            {et.fields.map((f, i) => (
              <FieldEditor
                key={i}
                field={f}
                onChange={updated => { const fields = [...et.fields]; fields[i] = updated; onChange({ ...et, fields }); }}
                onDelete={() => { const fields = et.fields.filter((_, idx) => idx !== i); onChange({ ...et, fields }); }}
              />
            ))}
            <button
              className="w-full mt-1 border border-dashed border-gray-300 dark:border-gray-700 rounded-lg py-1.5 text-sm text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:border-gray-400 dark:hover:border-gray-600 flex items-center justify-center gap-1"
              onClick={() => onChange({ ...et, fields: [...et.fields, blankField()] })}
            >
              <Plus className="w-3 h-3" /> Add field
            </button>
          </div>

          <div>
            <div className="text-xs text-gray-500 mb-2 uppercase tracking-wide">Sections</div>
            <div className="flex flex-wrap gap-2">
              {et.sections.map((s, i) => (
                <span key={i} className="inline-flex items-center gap-1 bg-gray-100 dark:bg-gray-800 dark:text-gray-300 rounded-full px-3 py-1 text-sm">
                  {s}
                  <button onClick={() => onChange({ ...et, sections: et.sections.filter((_, idx) => idx !== i) })} className="text-gray-400 hover:text-red-500">×</button>
                </span>
              ))}
              <form onSubmit={e => { e.preventDefault(); if (newSection.trim()) { onChange({ ...et, sections: [...et.sections, newSection.trim()] }); setNewSection(''); } }}>
                <input
                  className="border border-dashed border-gray-300 dark:border-gray-700 rounded-full px-3 py-1 text-sm w-28 dark:bg-gray-800 dark:text-white"
                  placeholder="+ section"
                  value={newSection}
                  onChange={e => setNewSection(e.target.value)}
                />
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ── Main SetupWizard component ────────────────────────────────────────────────

const SetupWizard: React.FC<SetupWizardProps> = ({ onComplete, onCancel, reconfigureMode = false, existingFolders = [] }) => {
  const [step, setStep] = useState(reconfigureMode ? 1 : 0);
  const [wikiName, setWikiName] = useState('');
  const [orgName, setOrgName] = useState('');
  const [orgDescription, setOrgDescription] = useState('');
  const [entityTypes, setEntityTypes] = useState<EntityType[]>([]);
  const [folderActions, setFolderActions] = useState<Record<string, 'keep' | 'delete'>>({});
  const [llmLoading, setLlmLoading] = useState(false);
  const [llmFailed, setLlmFailed] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState('');
  const [importLoading, setImportLoading] = useState(false);
  const [importError, setImportError] = useState('');

  // Prefill in reconfigure mode
  useEffect(() => {
    if (reconfigureMode) {
      fetch(`${API_BASE}/setup/config`)
        .then(r => r.json())
        .then(d => { setWikiName(d.wiki_name || ''); setOrgName(d.org_name || ''); })
        .catch(() => {});
      const initial: Record<string, 'keep' | 'delete'> = {};
      existingFolders.forEach(f => { initial[f] = 'keep'; });
      setFolderActions(initial);
    }
  }, [reconfigureMode, existingFolders]);

  // Auto-detect template import data written by SettingsDrawer before page reload
  useEffect(() => {
    if (reconfigureMode) return;
    const raw = sessionStorage.getItem('templateImport');
    if (!raw) return;
    sessionStorage.removeItem('templateImport');
    try {
      const data = JSON.parse(raw);
      if (data.wiki_name) setWikiName(data.wiki_name);
      if (data.org_name) setOrgName(data.org_name);
      if (data.org_description) setOrgDescription(data.org_description);
      const validTypes = Array.isArray(data.entity_types)
        ? data.entity_types.filter((et: any) =>
            et && typeof et.folder_name === 'string' && Array.isArray(et.fields) && Array.isArray(et.sections)
          )
        : [];
      if (validTypes.length > 0) {
        setEntityTypes(validTypes);
        setStep(2);
      }
    } catch {
      // Malformed sessionStorage entry — ignore and start fresh
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // intentionally mount-only: reconfigureMode is constant at mount time

  const handleGenerateSchema = async () => {
    setLlmLoading(true);
    setLlmFailed(false);
    try {
      const res = await fetch(`${API_BASE}/setup/suggest-schema`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ org_name: orgName, org_description: orgDescription }),
      });
      if (!res.ok) throw new Error('LLM unavailable');
      const data = await res.json();
      setEntityTypes(data.entity_types || []);
    } catch {
      setLlmFailed(true);
      setEntityTypes([]);
    } finally {
      setLlmLoading(false);
      setStep(2);
    }
  };

  const handleLaunch = async () => {
    setLaunching(true);
    setError('');
    try {
      // Delete folders marked for deletion (reconfigure mode)
      for (const [folder, action] of Object.entries(folderActions)) {
        if (action === 'delete') {
          await fetch(`${API_BASE}/setup/folder/${folder}`, { method: 'DELETE' });
        }
      }
      const res = await fetch(`${API_BASE}/setup/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          wiki_name: wikiName,
          org_name: orgName,
          org_description: orgDescription,
          entity_types: entityTypes,
        }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Setup failed');
      }
      onComplete();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Setup failed');
    } finally {
      setLaunching(false);
    }
  };

  const handleImportFile = () => {
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
        if (data.type === 'full') {
          window.location.reload();
          return;
        }
        // Template: pre-populate wizard with imported schema and jump to step 2
        if (data.wiki_name) setWikiName(data.wiki_name);
        if (data.org_name) setOrgName(data.org_name);
        if (data.org_description) setOrgDescription(data.org_description);
        const validTypes = Array.isArray(data.entity_types)
          ? data.entity_types.filter((et: any) =>
              et && typeof et.folder_name === 'string' && Array.isArray(et.fields) && Array.isArray(et.sections)
            )
          : [];
        if (validTypes.length > 0) setEntityTypes(validTypes);
        setStep(2);
      } catch {
        setImportError('Import failed. Please try again.');
      } finally {
        setImportLoading(false);
      }
    };
    input.click();
  };

  // ── Step 0: Getting Started ───────────────────────────────────────────────

  if (step === 0) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex items-center justify-center p-6">
        <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-8 w-full max-w-md border border-gray-200 dark:border-gray-800 relative">
          {onCancel && (
            <button
              onClick={onCancel}
              className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
              aria-label="Cancel setup"
            >
              <X className="w-5 h-5" />
            </button>
          )}
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">Get Started</h1>
          <p className="text-gray-500 dark:text-gray-400 mb-8">Set up your wiki from scratch or restore from a backup.</p>

          <div className="space-y-3">
            <button
              onClick={() => setStep(1)}
              className="w-full flex flex-col items-start gap-1 px-5 py-4 rounded-xl border-2 border-blue-500 bg-blue-50 dark:bg-blue-950/30 hover:bg-blue-100 dark:hover:bg-blue-950/50 transition-colors"
            >
              <span className="font-semibold text-blue-700 dark:text-blue-400">Start fresh</span>
              <span className="text-sm text-blue-500 dark:text-blue-500">Design your wiki schema from scratch or use a preset.</span>
            </button>

            <button
              onClick={handleImportFile}
              disabled={importLoading}
              className="w-full flex flex-col items-start gap-1 px-5 py-4 rounded-xl border-2 border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span className="font-semibold text-gray-700 dark:text-gray-300">
                {importLoading ? 'Importing…' : 'Import from backup'}
              </span>
              <span className="text-sm text-gray-400">Restore or start from a Faragopedia export file (.zip).</span>
            </button>
          </div>

          {importError && (
            <p className="mt-4 text-sm text-red-600 dark:text-red-400">{importError}</p>
          )}
        </div>
      </div>
    );
  }

  // ── Step 1: Identity ──────────────────────────────────────────────────────

  if (step === 1) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex items-center justify-center p-8">
        <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-800 w-full max-w-lg p-8 relative">
          {onCancel && (
            <button
              onClick={onCancel}
              className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
              aria-label="Cancel setup"
            >
              <X className="w-5 h-5" />
            </button>
          )}
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">{reconfigureMode ? 'Reconfigure Wiki' : 'Welcome — Set up your wiki'}</h1>
          <p className="text-gray-500 dark:text-gray-400 mb-6 text-sm">Tell us about your organisation. We'll generate a schema tailored to what you track.</p>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Wiki name</label>
              <input className="w-full border dark:border-gray-700 rounded-lg px-3 py-2 dark:bg-gray-800 dark:text-white" placeholder="e.g. Acme Wiki" value={wikiName} onChange={e => setWikiName(e.target.value)} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Organisation name</label>
              <input className="w-full border dark:border-gray-700 rounded-lg px-3 py-2 dark:bg-gray-800 dark:text-white" placeholder="e.g. Acme Corp" value={orgName} onChange={e => setOrgName(e.target.value)} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">What does your organisation do?</label>
              <textarea className="w-full border dark:border-gray-700 rounded-lg px-3 py-2 resize-none dark:bg-gray-800 dark:text-white" rows={4} placeholder="Describe your organisation and what kind of information you track..." value={orgDescription} onChange={e => setOrgDescription(e.target.value)} />
            </div>
          </div>

          <div className="flex gap-3">
            {reconfigureMode && onCancel && (
              <button
                onClick={onCancel}
                className="mt-6 flex-1 border border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-400 rounded-lg py-2.5 font-medium hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                Cancel
              </button>
            )}
            <button
              onClick={handleGenerateSchema}
              disabled={!wikiName.trim() || !orgName.trim() || !orgDescription.trim() || llmLoading}
              className={`mt-6 ${reconfigureMode ? 'flex-1' : 'w-full'} bg-blue-600 text-white rounded-lg py-2.5 font-medium hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center justify-center gap-2`}
            >
              {llmLoading ? <><Loader2 className="w-4 h-4 animate-spin" /> Generating schema...</> : 'Generate Schema →'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Step 2: Schema Review ──────────────────────────────────────────────────

  if (step === 2) {
    const matchedFolders = new Set(entityTypes.map(et => et.folder_name));

    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-950 p-8 relative">
        {onCancel && (
          <button
            onClick={onCancel}
            className="absolute top-6 right-6 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
            aria-label="Cancel setup"
          >
            <X className="w-5 h-5" />
          </button>
        )}
        <div className="max-w-4xl mx-auto">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-1">Review your schema</h1>
          <p className="text-gray-500 dark:text-gray-400 text-sm mb-6">Edit entity types, fields, and sections. Add or remove types as needed.</p>

          {llmFailed && (
            <div className="bg-yellow-50 dark:bg-yellow-900/10 border border-yellow-200 dark:border-yellow-900/30 rounded-lg p-4 mb-6">
              <p className="text-sm text-yellow-800 dark:text-yellow-400 mb-3">LLM unavailable — choose a preset to get started:</p>
              <div className="flex flex-wrap gap-2">
                {Object.keys(PRESETS).map(k => (
                  <button key={k} onClick={() => setEntityTypes(PRESETS[k])} className="px-3 py-1.5 rounded-lg border border-yellow-300 dark:border-yellow-700 text-sm text-yellow-800 dark:text-yellow-400 hover:bg-yellow-100 dark:hover:bg-yellow-900/30">{k}</button>
                ))}
              </div>
            </div>
          )}

          <div className={reconfigureMode ? 'flex gap-6' : ''}>
            <div className={reconfigureMode ? 'flex-1' : ''}>
              {reconfigureMode && <div className="text-xs text-gray-500 uppercase tracking-wide mb-3">New Schema</div>}
              {entityTypes.map((et, i) => {
                const badge = reconfigureMode
                  ? existingFolders.includes(et.folder_name) ? 'matches existing' : 'new'
                  : undefined;
                return (
                  <EntityCard
                    key={i}
                    et={et}
                    badge={badge}
                    onChange={updated => { const arr = [...entityTypes]; arr[i] = updated; setEntityTypes(arr); }}
                    onDelete={() => setEntityTypes(entityTypes.filter((_, idx) => idx !== i))}
                  />
                );
              })}
              <button
                onClick={() => setEntityTypes([...entityTypes, blankEntityType()])}
                className="w-full border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-xl py-4 text-gray-400 dark:text-gray-600 hover:text-gray-600 dark:hover:text-gray-400 hover:border-gray-400 dark:hover:border-gray-600 flex items-center justify-center gap-2"
              >
                <Plus className="w-4 h-4" /> Add entity type
              </button>
            </div>

            {reconfigureMode && (
              <div className="w-56 flex-shrink-0">
                <div className="text-xs text-gray-500 uppercase tracking-wide mb-3">Existing Folders</div>
                {existingFolders.map(folder => {
                  const matched = matchedFolders.has(folder);
                  return (
                    <div key={folder} className={`border rounded-lg p-3 mb-2 ${matched ? 'border-green-200 dark:border-green-900/30 bg-green-50 dark:bg-green-900/10' : 'border-red-200 dark:border-red-900/30 bg-red-50 dark:bg-red-900/10'}`}>
                      <div className="font-mono text-sm mb-1 text-gray-900 dark:text-gray-100">{folder}</div>
                      {matched ? (
                        <div className="text-xs text-green-600 dark:text-green-400">→ kept (matched)</div>
                      ) : (
                        <div className="flex gap-1 mt-1">
                          <button
                            onClick={() => setFolderActions(a => ({ ...a, [folder]: 'keep' }))}
                            className={`flex-1 text-xs py-1 rounded ${folderActions[folder] === 'keep' ? 'bg-green-600 text-white' : 'border border-green-400 dark:border-green-700 text-green-700 dark:text-green-400'}`}
                          >Keep</button>
                          <button
                            onClick={() => setFolderActions(a => ({ ...a, [folder]: 'delete' }))}
                            className={`flex-1 text-xs py-1 rounded ${folderActions[folder] === 'delete' ? 'bg-red-600 text-white' : 'border border-red-400 dark:border-red-700 text-red-700 dark:text-red-400'}`}
                          >Delete</button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="flex justify-between mt-6">
            <button onClick={() => setStep(1)} className="px-4 py-2 border dark:border-gray-700 rounded-lg text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800">← Back</button>
            <button
              onClick={() => setStep(3)}
              disabled={entityTypes.length === 0}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              Review & Launch →
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Step 3: Confirm ────────────────────────────────────────────────────────

  const toDelete = Object.entries(folderActions).filter(([, a]) => a === 'delete').map(([f]) => f);
  const toKeep = existingFolders.filter(f => folderActions[f] === 'keep' && !entityTypes.find(et => et.folder_name === f));

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex items-center justify-center p-8">
      <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-800 w-full max-w-lg p-8 relative">
        {onCancel && (
          <button
            onClick={onCancel}
            className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
            aria-label="Cancel setup"
          >
            <X className="w-5 h-5" />
          </button>
        )}
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">Ready to launch</h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm mb-6">Review what will be created, then click Launch Wiki.</p>

        <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-4 font-mono text-sm space-y-1 mb-4">
          <div className="font-bold text-gray-700 dark:text-gray-300 mb-2">{wikiName}</div>
          <div className="text-gray-500 dark:text-gray-400">wiki/</div>
          {entityTypes.map(et => (
            <div key={et.folder_name} className="text-green-700 dark:text-green-400 pl-2">+ {et.folder_name}/ <span className="text-gray-400 dark:text-gray-500">({et.fields.length} fields)</span></div>
          ))}
          {toKeep.map(f => <div key={f} className="text-blue-600 dark:text-blue-400 pl-2">~ {f}/ <span className="text-gray-400 dark:text-gray-500">(kept)</span></div>)}
          {toDelete.map(f => <div key={f} className="text-red-500 dark:text-red-400 pl-2">- {f}/ <span className="text-gray-400 dark:text-gray-500">(deleted)</span></div>)}
        </div>

        {error && <div className="bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-900/30 rounded-lg p-3 text-red-700 dark:text-red-400 text-sm mb-4">{error}</div>}

        <div className="flex gap-3">
          <button onClick={() => setStep(2)} className="px-4 py-2 border dark:border-gray-700 rounded-lg text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800">← Back</button>
          <button
            onClick={handleLaunch}
            disabled={launching}
            className="flex-1 bg-blue-600 text-white rounded-lg py-2.5 font-medium hover:bg-blue-700 disabled:bg-gray-300 flex items-center justify-center gap-2"
          >
            {launching ? <><Loader2 className="w-4 h-4 animate-spin" /> Launching...</> : 'Launch Wiki'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SetupWizard;

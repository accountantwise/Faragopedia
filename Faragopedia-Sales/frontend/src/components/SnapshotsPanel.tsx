import React, { useState, useEffect, useCallback } from 'react';
import { ChevronDown, ChevronRight, RotateCcw, Trash2, Loader2 } from 'lucide-react';
import { API_BASE } from '../config';

interface Snapshot {
  id: string;
  label: string;
  created_at: string;
  file_count: number;
}

const SnapshotsPanel: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmRestore, setConfirmRestore] = useState<string | null>(null);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  const fetchSnapshots = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/snapshots`);
      if (!res.ok) throw new Error('Failed to load snapshots');
      setSnapshots(await res.json());
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) fetchSnapshots();
  }, [open, fetchSnapshots]);

  const restoreSnapshot = async (id: string) => {
    setActionInProgress(id);
    setConfirmRestore(null);
    try {
      const res = await fetch(`${API_BASE}/snapshots/${id}/restore`, { method: 'POST' });
      if (!res.ok) throw new Error('Restore failed');
      setError(null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActionInProgress(null);
    }
  };

  const deleteSnapshot = async (id: string) => {
    setActionInProgress(id);
    try {
      const res = await fetch(`${API_BASE}/snapshots/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Delete failed');
      setSnapshots(prev => prev.filter(s => s.id !== id));
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActionInProgress(null);
    }
  };

  return (
    <div className="mt-12 border border-gray-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-5 py-4 bg-gray-50 hover:bg-gray-100 transition-colors text-sm font-semibold text-gray-700"
      >
        <span>Snapshots</span>
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
      </button>

      {open && (
        <div className="p-5">
          {loading && (
            <div className="flex items-center gap-2 text-gray-500 text-sm">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading snapshots...
            </div>
          )}

          {error && (
            <p className="text-red-600 text-sm">{error}</p>
          )}

          {!loading && snapshots.length === 0 && (
            <p className="text-gray-400 text-sm">No snapshots yet. Snapshots are created automatically before applying lint fixes.</p>
          )}

          {snapshots.length > 0 && (
            <ul className="space-y-2">
              {snapshots.map(snap => (
                <li key={snap.id} className="flex items-center justify-between p-3 bg-white border border-gray-100 rounded-lg">
                  <div>
                    <p className="text-sm font-medium text-gray-800">{snap.label}</p>
                    <p className="text-xs text-gray-400">{new Date(snap.created_at).toLocaleString()} · {snap.file_count} files</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {confirmRestore === snap.id ? (
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-amber-700 font-medium">Overwrite current wiki?</span>
                        <button
                          onClick={() => restoreSnapshot(snap.id)}
                          className="px-3 py-1 bg-amber-600 text-white rounded-lg hover:bg-amber-700 text-xs font-semibold"
                        >
                          Yes, restore
                        </button>
                        <button
                          onClick={() => setConfirmRestore(null)}
                          className="px-3 py-1 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 text-xs font-semibold"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <>
                        <button
                          onClick={() => setConfirmRestore(snap.id)}
                          disabled={actionInProgress === snap.id}
                          className="flex items-center gap-1 px-3 py-1 text-xs font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-lg disabled:opacity-50"
                        >
                          {actionInProgress === snap.id
                            ? <Loader2 className="w-3 h-3 animate-spin" />
                            : <RotateCcw className="w-3 h-3" />
                          }
                          Restore
                        </button>
                        <button
                          onClick={() => deleteSnapshot(snap.id)}
                          disabled={actionInProgress === snap.id}
                          className="flex items-center gap-1 px-3 py-1 text-xs font-semibold text-red-600 bg-red-50 hover:bg-red-100 rounded-lg disabled:opacity-50"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

export default SnapshotsPanel;

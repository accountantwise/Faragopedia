import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check, Plus, MoreHorizontal, Copy, Archive, RotateCcw, ChevronRight, Pencil, Trash2 } from 'lucide-react';
import DuplicateWorkspaceModal from './DuplicateWorkspaceModal';
import DeleteWorkspaceModal from './DeleteWorkspaceModal';
import RenameWorkspaceModal from './RenameWorkspaceModal';
import octopusMark from '../assets/octopus-mark-white.svg';

interface Workspace {
  id: string;
  name: string;
  archived?: boolean;
}

interface WorkspaceSwitcherProps {
  workspaces: Workspace[];
  activeWorkspaceId: string;
  onSwitch: (id: string) => void;
  onNewWorkspace: () => void;
  onArchive: (id: string) => void;
  onUnarchive: (id: string) => void;
  onDuplicate: (id: string, name: string, mode: 'full' | 'template') => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onRename: (id: string, name: string) => Promise<void>;
}

const WorkspaceSwitcher: React.FC<WorkspaceSwitcherProps> = ({
  workspaces,
  activeWorkspaceId,
  onSwitch,
  onNewWorkspace,
  onArchive,
  onUnarchive,
  onDuplicate,
  onDelete,
  onRename,
}) => {
  const [open, setOpen] = useState(false);
  const [contextMenuId, setContextMenuId] = useState<string | null>(null);
  const [archivedExpanded, setArchivedExpanded] = useState(false);
  const [duplicateSource, setDuplicateSource] = useState<Workspace | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Workspace | null>(null);
  const [renameTarget, setRenameTarget] = useState<Workspace | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setContextMenuId(null);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const activeWs = workspaces.find(ws => ws.id === activeWorkspaceId);
  const displayName = activeWs?.name ?? 'Workspace';
  const activeWorkspaces = workspaces.filter(ws => !ws.archived);
  const archivedWorkspaces = workspaces.filter(ws => ws.archived);

  const handleContextMenu = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    setContextMenuId(prev => (prev === id ? null : id));
  };

  return (
    <>
      <div ref={ref} className="relative">
        {/* Trigger button */}
        <button
          onClick={() => { setOpen(prev => !prev); setContextMenuId(null); }}
          className="w-full flex items-center gap-3 px-6 py-4 text-left hover:bg-gray-700 transition-colors border-b border-gray-700"
        >
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center shrink-0">
            <img src={octopusMark} alt="" aria-hidden="true" className="w-6 h-6" />
          </div>
          <span className="flex-grow font-bold text-xl truncate">{displayName}</span>
          <ChevronDown
            className={`w-4 h-4 text-gray-400 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
          />
        </button>

        {/* Dropdown */}
        {open && (
          <div className="absolute left-0 right-0 bg-gray-700 border border-gray-600 rounded-b-lg shadow-xl z-50">

            {/* Active workspaces */}
            {activeWorkspaces.map(ws => (
              <div key={ws.id} className="relative group flex items-center">
                <button
                  onClick={() => { onSwitch(ws.id); setOpen(false); }}
                  className="flex-grow flex items-center justify-between px-4 py-3 text-left text-sm hover:bg-gray-600 transition-colors min-w-0"
                >
                  <span className="truncate">{ws.name}</span>
                  {ws.id === activeWorkspaceId && (
                    <Check className="w-4 h-4 text-blue-400 shrink-0 ml-2" />
                  )}
                </button>

                {/* Context menu trigger */}
                <button
                  onClick={e => handleContextMenu(e, ws.id)}
                  className="px-2 py-3 text-gray-400 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                  title="More options"
                >
                  <MoreHorizontal className="w-4 h-4" />
                </button>

                {/* Context menu popover */}
                {contextMenuId === ws.id && (
                  <div className="absolute right-0 top-full mt-1 bg-gray-800 border border-gray-600 rounded-lg shadow-xl z-10 w-40 py-1">
                    <button
                      onClick={e => {
                        e.stopPropagation();
                        setRenameTarget(ws);
                        setContextMenuId(null);
                        setOpen(false);
                      }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-700 transition-colors"
                    >
                      <Pencil className="w-4 h-4" />
                      Rename
                    </button>
                    <button
                      onClick={e => {
                        e.stopPropagation();
                        setDuplicateSource(ws);
                        setContextMenuId(null);
                        setOpen(false);
                      }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-700 transition-colors"
                    >
                      <Copy className="w-4 h-4" />
                      Duplicate
                    </button>
                    {ws.id === activeWorkspaceId ? (
                      <button
                        disabled
                        title="Switch to another workspace first"
                        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-500 cursor-not-allowed"
                      >
                        <Archive className="w-4 h-4" />
                        Archive
                      </button>
                    ) : (
                      <button
                        onClick={e => {
                          e.stopPropagation();
                          onArchive(ws.id);
                          setContextMenuId(null);
                        }}
                        className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-700 transition-colors"
                      >
                        <Archive className="w-4 h-4" />
                        Archive
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}

            {/* Archived section */}
            {archivedWorkspaces.length > 0 && (
              <div className="border-t border-gray-600">
                <button
                  onClick={() => setArchivedExpanded(prev => !prev)}
                  className="w-full flex items-center justify-between px-4 py-2 text-xs text-gray-400 hover:bg-gray-600 transition-colors"
                >
                  <span>Archived · {archivedWorkspaces.length}</span>
                  <ChevronRight className={`w-3 h-3 transition-transform ${archivedExpanded ? 'rotate-90' : ''}`} />
                </button>

                {archivedExpanded && archivedWorkspaces.map(ws => (
                  <div key={ws.id} className="relative group flex items-center bg-gray-750">
                    <span className="flex-grow px-4 py-2 text-sm text-gray-400 truncate">{ws.name}</span>
                    <button
                      onClick={e => handleContextMenu(e, ws.id)}
                      className="px-2 py-2 text-gray-500 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                    >
                      <MoreHorizontal className="w-4 h-4" />
                    </button>
                    {contextMenuId === ws.id && (
                      <div className="absolute right-0 top-full mt-1 bg-gray-800 border border-gray-600 rounded-lg shadow-xl z-10 w-40 py-1">
                        <button
                          onClick={e => {
                            e.stopPropagation();
                            onUnarchive(ws.id);
                            setContextMenuId(null);
                          }}
                          className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-700 transition-colors"
                        >
                          <RotateCcw className="w-4 h-4" />
                          Restore
                        </button>
                        <div className="border-t border-gray-700 my-1" />
                        <button
                          onClick={e => {
                            e.stopPropagation();
                            setDeleteTarget(ws);
                            setContextMenuId(null);
                            setOpen(false);
                          }}
                          className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-gray-700 hover:text-red-300 transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                          Delete permanently
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* New workspace */}
            <div className="border-t border-gray-600">
              <button
                onClick={() => { onNewWorkspace(); setOpen(false); }}
                className="w-full flex items-center gap-2 px-4 py-3 text-sm text-blue-400 hover:bg-gray-600 transition-colors"
              >
                <Plus className="w-4 h-4" />
                New Workspace
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Duplicate modal — rendered outside the dropdown div so it's not clipped */}
      {duplicateSource && (
        <DuplicateWorkspaceModal
          sourceName={duplicateSource.name}
          onClose={() => setDuplicateSource(null)}
          onConfirm={async (name, mode) => {
            await onDuplicate(duplicateSource.id, name, mode);
            setDuplicateSource(null);
          }}
        />
      )}

      {renameTarget && (
        <RenameWorkspaceModal
          currentName={renameTarget.name}
          onClose={() => setRenameTarget(null)}
          onConfirm={async (name) => {
            await onRename(renameTarget.id, name);
            setRenameTarget(null);
          }}
        />
      )}

      {deleteTarget && (
        <DeleteWorkspaceModal
          workspaceName={deleteTarget.name}
          onClose={() => setDeleteTarget(null)}
          onConfirm={async () => {
            await onDelete(deleteTarget.id);
            setDeleteTarget(null);
          }}
        />
      )}
    </>
  );
};

export default WorkspaceSwitcher;

import React, { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { FileText, ChevronRight, Loader2, FileCheck, Trash2, Download, ArrowLeft, ArrowRight, Plus, Database, MoreVertical, X, Search, ListChecks } from 'lucide-react';

import { API_BASE } from '../config';
import { useOperationToasts } from '../OperationToastContext';
import ErrorToast from './ErrorToast';
import AddSourcesModal from './AddSourcesModal';
import ConfirmDialog from './ConfirmDialog';

type SourceEntry = {
  filename: string;
  display_name: string;
  tags: string[];
  metadata: { ingested: boolean; upload_date: string | null };
};

type Props = {
  sourcesMetadata: Record<string, { ingested: boolean; ingested_at: string | null; tags: string[] }>;
};

const SourcesView: React.FC<Props> = ({ sourcesMetadata }) => {
  const [sources, setSources] = useState<string[]>([]);
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [historyStack, setHistoryStack] = useState<string[]>([]);
  const [forwardStack, setForwardStack] = useState<string[]>([]);
  const [ingesting, setIngesting] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());
  const [hoveredItem, setHoveredItem] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);

  const [loading, setLoading] = useState<boolean>(true);
  const [contentLoading, setContentLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [isDeleting, setIsDeleting] = useState<boolean>(false);

  // Search and tags state
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [sourceIndex, setSourceIndex] = useState<SourceEntry[]>([]);
  const [tagFilter, setTagFilter] = useState<string[]>([]);
  const [sourceTags, setSourceTags] = useState<string[]>([]);
  const [tagVocabulary, setTagVocabulary] = useState<string[]>([]);
  const [addingTag, setAddingTag] = useState(false);
  const [newTagInput, setNewTagInput] = useState('');
  const [isBulkMode, setIsBulkMode] = useState(false);

  // Resizable sidebar state
  const [sidebarWidth, setSidebarWidth] = useState<number>(256);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);

  // Polling refs for async source ingestion
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Mobile/Tablet responsive states
  const [isDesktop, setIsDesktop] = useState(window.innerWidth >= 1024);
  const [showMobileList, setShowMobileList] = useState(true);
  const [showActionMenu, setShowActionMenu] = useState(false);

  const { startIngest, failIngest } = useOperationToasts();

  const stopPolling = () => {
    if (pollingIntervalRef.current) { clearInterval(pollingIntervalRef.current); pollingIntervalRef.current = null; }
    if (pollingTimeoutRef.current) { clearTimeout(pollingTimeoutRef.current); pollingTimeoutRef.current = null; }
  };

  const startPolling = (knownCount: number) => {
    stopPolling();
    pollingIntervalRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/sources`);
        if (!res.ok) return;
        const data: string[] = await res.json();
        if (data.length > knownCount) {
          stopPolling();
          fetchSources();
          fetchSourceIndex();
        }
      } catch {}
    }, 4000);
    // Safety valve — stop polling after 90 seconds regardless
    pollingTimeoutRef.current = setTimeout(stopPolling, 90000);
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    dragRef.current = { startX: e.clientX, startWidth: sidebarWidth };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!dragRef.current) return;
    const { startX, startWidth } = dragRef.current;
    const newWidth = Math.min(Math.max(200, startWidth + (e.clientX - startX)), 800);
    setSidebarWidth(newWidth);
  }, []);

  const handleMouseUp = useCallback(() => {
    if (dragRef.current) {
      dragRef.current = null;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }
  }, []);

  useEffect(() => {
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    
    // Track window resizes for responsive layout
    const handleResize = () => setIsDesktop(window.innerWidth >= 1024);
    window.addEventListener('resize', handleResize);
    
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      window.removeEventListener('resize', handleResize);
      stopPolling();
    };
  }, [handleMouseMove, handleMouseUp]);

  useEffect(() => {
    if (!selectedSource) { setSourceTags([]); return; }
    const entry = sourceIndex.find(s => s.filename === selectedSource);
    setSourceTags(entry?.tags ?? []);
  }, [selectedSource, sourceIndex]);

  useEffect(() => {
    fetchSources();
    fetchSourceIndex();
    fetchTagVocabulary();
  }, []);

  const toggleSelection = (filename: string) => {
    setSelectedItems(prev => {
      const next = new Set(prev);
      if (next.has(filename)) next.delete(filename); else next.add(filename);
      return next;
    });
  };

  const selectAll = () => {
    // Select based on current search results if searching, otherwise all sources
    const visible = searchResults ? searchResults.map(s => s.filename) : sources;
    setSelectedItems(new Set(visible));
  };

  const clearSelection = () => { setSelectedItems(new Set()); setIsBulkMode(false); };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') clearSelection();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const parseFrontmatter = (text: string) => {
    const match = text.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
    if (match) {
      const frontmatterText = match[1];
      const restContent = match[2];
      const tags: {key: string, value: string}[] = [];
      frontmatterText.split('\n').forEach(line => {
        const colonIdx = line.indexOf(':');
        if (colonIdx > -1) {
          const key = line.substring(0, colonIdx).trim();
          const val = line.substring(colonIdx + 1).trim();
          if (key && val) tags.push({ key, value: val });
        }
      });
      return { tags, content: restContent };
    }
    return { tags: [], content: text };
  };

  const fetchSources = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE}/sources`);
      if (!response.ok) throw new Error('Failed to fetch sources');
      const data = await response.json();
      setSources(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchSourceIndex = async () => {
    try {
      const res = await fetch(`${API_BASE}/search/index`);
      if (!res.ok) return;
      const data = await res.json();
      setSourceIndex(data.sources || []);
    } catch {}
  };

  const fetchTagVocabulary = async () => {
    try {
      const res = await fetch(`${API_BASE}/tags`);
      if (!res.ok) return;
      const data: Record<string, number> = await res.json();
      setTagVocabulary(Object.keys(data).sort());
    } catch {}
  };

  const fetchSourceContent = async (filename: string, addToHistory: boolean = true) => {
    try {
      setContentLoading(true);
      
      if (addToHistory && selectedSource && selectedSource !== filename) {
        setHistoryStack(prev => [...prev, selectedSource]);
        setForwardStack([]);
      }

      setSelectedSource(filename);
      
      const response = await fetch(`${API_BASE}/sources/${encodeURIComponent(filename)}`);
      if (!response.ok) throw new Error('Failed to fetch source content');
      
      const data = await response.json();
      setContent(data.content);
      
      // Auto-switch away from list view on small screens
      setShowMobileList(false);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setContentLoading(false);
    }
  };

  const handleBack = () => {
    if (historyStack.length === 0) return;
    const previous = historyStack[historyStack.length - 1];
    setHistoryStack(prev => prev.slice(0, -1));
    if (selectedSource) setForwardStack(prev => [selectedSource, ...prev]);
    fetchSourceContent(previous, false);
  };

  const handleForward = () => {
    if (forwardStack.length === 0) return;
    const next = forwardStack[0];
    setForwardStack(prev => prev.slice(1));
    if (selectedSource) setHistoryStack(prev => [...prev, selectedSource]);
    fetchSourceContent(next, false);
  };

  const handleIngest = async () => {
    if (!selectedSource) return;
    try {
      setIngesting(selectedSource);
      startIngest([selectedSource]);
      const response = await fetch(`${API_BASE}/sources/${encodeURIComponent(selectedSource)}/ingest`, {
        method: 'POST'
      });
      if (!response.ok) {
        failIngest(selectedSource);
        throw new Error('Failed to start ingestion');
      }
      // Completion detected by App.tsx metadata poll
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIngesting(null);
    }
  };

  const handleDelete = async () => {
    if (!selectedSource) return;
    if (!window.confirm(`Move source '${selectedSource}' to archive?`)) return;

    try {
      setIsDeleting(true);
      const response = await fetch(`${API_BASE}/sources/${encodeURIComponent(selectedSource)}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error('Failed to delete source');
      
      setSelectedSource(null);
      setContent(null);
      fetchSources();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleDownload = () => {
    if (!selectedSource) return;
    window.open(`${API_BASE}/sources/${encodeURIComponent(selectedSource)}/download`);
  };

  const handleBulkIngest = async () => {
    const filenames = Array.from(selectedItems);
    try {
      startIngest(filenames);
      await fetch(`${API_BASE}/sources/bulk-ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filenames }),
      });
      clearSelection();
    } catch {
      filenames.forEach(f => failIngest(f));
      setError('Failed to start bulk ingestion');
    }
  };

  const handleBulkArchive = async () => {
    setShowConfirm(false);
    try {
      const res = await fetch(`${API_BASE}/sources/bulk`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filenames: Array.from(selectedItems) }),
      });
      const data = await res.json();
      if (data.errors?.length) {
        setError(`Failed to archive: ${data.errors.join(', ')}`);
      }
      clearSelection();
      fetchSources();
    } catch {
      setError('Failed to archive selected sources');
    }
  };

  const handleBulkDownloadSources = async () => {
    try {
      const res = await fetch(`${API_BASE}/sources/bulk-download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filenames: Array.from(selectedItems) }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setError(err.detail ?? 'Failed to download sources');
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'sources-export.zip';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      setError('Failed to download selected sources');
    }
  };

  const searchResults: SourceEntry[] | null = (() => {
    if (!searchQuery.trim()) return null;
    const q = searchQuery.toLowerCase();
    return sourceIndex.filter(src => {
      const matchesQuery =
        src.filename.toLowerCase().includes(q) ||
        src.tags.some(t => t.toLowerCase().includes(q));
      const matchesTags =
        tagFilter.length === 0 || tagFilter.every(t => src.tags.includes(t));
      return matchesQuery && matchesTags;
    });
  })();

  const resultTags: string[] = (() => {
    if (!searchResults) return [];
    const all = new Set<string>();
    searchResults.forEach(r => r.tags.forEach(t => all.add(t)));
    return Array.from(all).sort();
  })();

  const handleAddSourceTag = async (tag: string) => {
    const trimmed = tag.toLowerCase().trim();
    if (!trimmed || sourceTags.includes(trimmed) || !selectedSource) return;
    const newTags = [...sourceTags, trimmed];
    setSourceTags(newTags);
    setAddingTag(false);
    setNewTagInput('');
    try {
      await fetch(`${API_BASE}/sources/${encodeURIComponent(selectedSource)}/tags`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags: newTags }),
      });
      fetchSourceIndex();
      fetchTagVocabulary();
    } catch { setSourceTags(sourceTags); }
  };

  const handleRemoveSourceTag = async (tag: string) => {
    if (!selectedSource) return;
    const newTags = sourceTags.filter(t => t !== tag);
    setSourceTags(newTags);
    try {
      await fetch(`${API_BASE}/sources/${encodeURIComponent(selectedSource)}/tags`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags: newTags }),
      });
      fetchSourceIndex();
    } catch { setSourceTags(sourceTags); }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="animate-spin mr-2" /> Loading Sources...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full relative">
      {/* Search bar */}
      <div className="border-b border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 px-4 py-2 flex items-center gap-3">
        <Search className="w-4 h-4 text-gray-400 shrink-0" />
        <input
          type="text"
          value={searchQuery}
          onChange={e => { setSearchQuery(e.target.value); setTagFilter([]); }}
          placeholder="Search sources…"
          className="flex-1 bg-transparent text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 outline-none"
        />
        {searchQuery && (
          <button onClick={() => { setSearchQuery(''); setTagFilter([]); }}
                  className="text-gray-500 hover:text-gray-300">
            <X className="w-4 h-4" />
          </button>
        )}
        {searchResults && (
          <span className="text-xs text-gray-500 shrink-0">
            {searchResults.length} result{searchResults.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      <div className="flex flex-1 min-h-0 relative">
      {/* Sidebar - Source List */}
      <div 
        className={`border-r dark:border-gray-800 bg-white dark:bg-gray-900 flex flex-col flex-shrink-0 ${!isDesktop && !showMobileList ? 'hidden' : 'flex'} ${!isDesktop ? 'w-full' : ''}`}
        style={isDesktop ? { width: sidebarWidth } : undefined}
      >
        <div className="p-4 border-b border-gray-50 dark:border-gray-800 flex-shrink-0">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Sources</h2>
            <button
              onClick={() => setShowAddModal(true)}
              className="p-1.5 bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors"
              title="Add Source"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
        </div>
        
        {/* Bulk Action Toolbar - Now Sticky at Top */}
        {(selectedItems.size > 0 || isBulkMode) && (
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-gray-100 rounded-xl p-3 mb-2 shadow-sm animate-in slide-in-from-top-2 duration-300 mx-4">
            <div className="flex items-center justify-between mb-3 px-1">
              <span className="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase tracking-widest">{selectedItems.size} Selected</span>
              <button 
                onClick={clearSelection} 
                className="text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full"
                title="Clear selection"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex flex-col gap-2">
              <button
                onClick={selectAll}
                className="w-full text-[10px] py-1 bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-400 rounded hover:bg-gray-100 dark:hover:bg-gray-600 transition-all font-medium uppercase tracking-tight"
              >
                Select {searchResults ? 'matching' : 'all'}
              </button>
              <div className="grid grid-cols-3 gap-2">
                <button
                  onClick={handleBulkIngest}
                  className="flex items-center justify-center gap-2 text-xs py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 shadow-sm transition-all font-bold"
                >
                  <Database className="w-3.5 h-3.5" />
                  Ingest
                </button>
                <button
                  onClick={handleBulkDownloadSources}
                  className="flex items-center justify-center gap-2 text-xs py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-500 shadow-sm transition-all font-bold"
                >
                  <Download className="w-3.5 h-3.5" />
                  Download
                </button>
                <button
                  onClick={() => setShowConfirm(true)}
                  className="flex items-center justify-center gap-2 text-xs py-2 bg-red-600 text-white rounded-lg hover:bg-red-500 shadow-sm transition-all font-bold"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  Archive
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-0 mt-2">
        {searchResults !== null ? (
          <div className="flex flex-col">
            {resultTags.length > 0 && (
              <div className="flex flex-wrap gap-1 px-3 py-2 border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/50">
                <span className="text-xs text-gray-500 dark:text-gray-400 self-center mr-1">Filter:</span>
                {resultTags.map(tag => (
                  <button key={tag}
                          onClick={() => setTagFilter(prev =>
                            prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]
                          )}
                          className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                            tagFilter.includes(tag)
                              ? 'bg-blue-600 border-blue-500 text-white'
                              : 'bg-gray-100 dark:bg-gray-700 border-gray-200 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:border-gray-300 dark:hover:border-gray-500'
                          }`}>
                    {tagFilter.includes(tag) ? `${tag} ×` : tag}
                  </button>
                ))}
              </div>
            )}
            <div className="divide-y divide-gray-50/50 dark:divide-gray-800/50">
              {searchResults.length === 0 ? (
                <p className="text-sm text-gray-500 dark:text-gray-400 p-4">No sources match.</p>
              ) : (
                searchResults.map(entry => (
                  <div 
                    key={entry.filename}
                    className="group flex items-center px-4 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors border-b border-gray-50 dark:border-gray-800"
                    onMouseEnter={() => setHoveredItem(entry.filename)}
                    onMouseLeave={() => setHoveredItem(null)}
                  >
                    <div className="w-6 shrink-0 flex justify-start items-start pt-3">
                      {(hoveredItem === entry.filename || selectedItems.size > 0 || isBulkMode) && (
                        <input
                          type="checkbox"
                          checked={selectedItems.has(entry.filename)}
                          onChange={() => toggleSelection(entry.filename)}
                          onClick={e => e.stopPropagation()}
                          className="w-4 h-4 accent-blue-600 cursor-pointer shadow-sm hover:scale-110 transition-transform"
                        />
                      )}
                    </div>
                    <button
                      onClick={() => { fetchSourceContent(entry.filename); setSearchQuery(''); setTagFilter([]); }}
                      className="flex-1 text-left py-3 min-w-0 pr-2"
                    >
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1 truncate">{entry.filename}</div>
                      {entry.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {entry.tags.map(t => (
                            <span key={t} className="text-[10px] px-2.5 py-1 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-medium uppercase tracking-tight whitespace-nowrap">{t}</span>
                          ))}
                        </div>
                      )}
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        ) : (
          sources.length === 0 ? (
            <p className="text-gray-500 text-sm p-4">No source files found. Upload some data!</p>
          ) : (
            <ul className="space-y-1 pb-4">
              {sources.map((source) => (
                <li 
                  key={source}
                  className="relative group flex items-center"
                  onMouseEnter={() => setHoveredItem(source)}
                  onMouseLeave={() => setHoveredItem(null)}
                >
                  {(hoveredItem === source || selectedItems.size > 0 || isBulkMode) && (
                    <input
                      type="checkbox"
                      checked={selectedItems.has(source)}
                      onChange={() => toggleSelection(source)}
                      onClick={e => e.stopPropagation()}
                      className="absolute left-3 z-10 w-4 h-4 accent-blue-600 cursor-pointer shadow-sm hover:scale-110 transition-transform"
                    />
                  )}
                    <button
                      onClick={() => fetchSourceContent(source)}
                      className={`w-full text-left py-2.5 pl-9 pr-3 rounded-lg text-sm transition-colors flex items-center justify-between ${
                        selectedSource === source
                          ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-bold'
                          : 'hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300'
                      }`}
                    >
                    <span className="flex items-start text-left max-w-[88%] min-w-0">
                      <FileCheck className={`w-4 h-4 mr-2 mt-0.5 shrink-0 ${sourcesMetadata[source]?.ingested ? 'text-green-500' : 'text-gray-400 opacity-40'}`} />
                      <span className="break-all line-clamp-2">{source}</span>
                    </span>
                    {selectedSource === source && <ChevronRight className="w-4 h-4" />}
                  </button>
                </li>
              ))}
            </ul>
          )
        )}
        
        </div>
      </div>

      {/* Drag Handle Gutter */}
      {isDesktop && (
        <div
          onMouseDown={handleMouseDown}
          className="w-1 bg-transparent hover:bg-blue-400 cursor-col-resize transition-colors z-20 flex-shrink-0"
        />
      )}

      {/* Main Content - Source View */}
      <div className={`flex-grow overflow-y-auto bg-white dark:bg-gray-900 flex-col ${!isDesktop && showMobileList ? 'hidden' : 'flex'}`}>
        {/* Navigation Header */}
        <div className="hidden lg:flex border-b dark:border-gray-800 px-8 py-4 items-center justify-between sticky top-0 bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm z-10">
          <div className="flex items-center space-x-2">
            <button
              onClick={handleBack}
              disabled={historyStack.length === 0}
              className={`p-1.5 rounded-md transition-colors ${
                historyStack.length === 0 ? 'text-gray-300 dark:text-gray-700 cursor-not-allowed' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
              title="Back"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <button
              onClick={handleForward}
              disabled={forwardStack.length === 0}
              className={`p-1.5 rounded-md transition-colors ${
                forwardStack.length === 0 ? 'text-gray-300 dark:text-gray-700 cursor-not-allowed' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
              title="Forward"
            >
              <ArrowRight className="w-5 h-5" />
            </button>
            {selectedSource && (
              <div className="flex items-center ml-4 space-x-3 min-w-0">
                <span className="text-sm font-medium text-gray-500 dark:text-gray-400 truncate max-w-[160px] sm:max-w-xs">
                  {selectedSource}
                </span>
                {sourcesMetadata[selectedSource]?.ingested ? (
                  <span className="flex items-center px-2 py-0.5 rounded-full bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-400 text-[10px] font-bold uppercase tracking-wider border border-green-100 dark:border-green-800">
                    <Database className="w-3 h-3 mr-1" />
                    Ingested
                  </span>
                ) : (
                  <span className="flex items-center px-2 py-0.5 rounded-full bg-amber-50 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 text-[10px] font-bold uppercase tracking-wider border border-amber-100 dark:border-amber-800">
                    Pending
                  </span>
                )
                }
              </div>
            )}
          </div>
          
          {selectedSource && (
            <div className="flex items-center space-x-2">
              {selectedItems.size === 0 && (
                <>
                  {!sourcesMetadata[selectedSource]?.ingested && (
                    <button
                      onClick={handleIngest}
                      disabled={!!ingesting}
                      className="flex items-center px-3 py-1.5 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 transition-colors disabled:bg-blue-400"
                    >
                      {ingesting === selectedSource ? (
                        <Loader2 className="w-4 h-4 animate-spin mr-1.5" />
                      ) : (
                        <Database className="w-4 h-4 mr-1.5" />
                      )}
                      {ingesting === selectedSource ? 'Ingesting...' : 'Ingest'}
                    </button>
                  )}
                  <button
                    onClick={handleDownload}
                    className="p-1.5 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors"
                    title="Download Source"
                  >
                    <Download className="w-5 h-5" />
                  </button>
                  <button
                    onClick={handleDelete}
                    disabled={isDeleting}
                    className="p-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-md transition-colors disabled:opacity-50"
                    title="Move to Archive"
                  >
                    {isDeleting ? <Loader2 className="w-5 h-5 animate-spin" /> : <Trash2 className="w-5 h-5" />}
                  </button>
                </>
              )}
              {selectedItems.size > 0 && (
                <span className="text-xs font-semibold text-amber-600 bg-amber-50 px-3 py-1.5 rounded-md border border-amber-100">
                  Bulk mode active
                </span>
              )}
            </div>
          )}
        </div>

        {selectedSource && (
          <div className="flex flex-wrap items-center gap-1.5 px-6 pb-3 pt-1 border-b border-gray-100 dark:border-gray-800 bg-gray-50/30 dark:bg-gray-800/30">
            {sourceTags.map(tag => (
              <span key={tag}
                    className="inline-flex items-center gap-1 text-xs px-3 py-1 rounded-full bg-blue-50 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 border border-blue-100 dark:border-blue-800 shadow-sm font-medium">
                {tag}
                <button onClick={() => handleRemoveSourceTag(tag)} className="text-blue-500 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-200">×</button>
              </span>
            ))}
            {addingTag ? (
              <div className="relative">
                <input autoFocus value={newTagInput}
                       onChange={e => setNewTagInput(e.target.value)}
                       onKeyDown={e => {
                         if (e.key === 'Enter') handleAddSourceTag(newTagInput);
                         if (e.key === 'Escape') { setAddingTag(false); setNewTagInput(''); }
                       }}
                       placeholder="tag name"
                       className="text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded px-2 py-0.5 text-gray-900 dark:text-gray-100 outline-none w-28"
                       list="source-tag-vocab" />
                <datalist id="source-tag-vocab">
                  {tagVocabulary.filter(t => !sourceTags.includes(t)).map(t => <option key={t} value={t} />)}
                </datalist>
              </div>
            ) : (
              <button onClick={() => setAddingTag(true)} className="text-xs text-gray-500 hover:text-gray-300 px-1">+ tag</button>
            )}
          </div>
        )}

        <div className="p-8 flex-grow pb-28 lg:pb-8 min-w-0 overflow-x-hidden">
          {contentLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="animate-spin mr-2" /> Loading source content...
            </div>
          ) : content ? (
            selectedSource?.endsWith('.md') ? (
              <div className="prose prose-slate dark:prose-invert max-w-4xl mx-auto break-words text-gray-900 dark:text-gray-100">
                {(() => {
                   const { tags, content: cleanContent } = parseFrontmatter(content);
                   return (
                     <>
                       {tags.length > 0 && (
                         <div className="flex flex-wrap gap-2 mb-8 p-4 bg-gray-50/80 dark:bg-gray-800/80 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm backdrop-blur-sm">
                           {tags.map((t, idx) => (
                             <span key={idx} className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 shadow-sm uppercase tracking-wider">
                               <span className="text-gray-400 dark:text-gray-500 mr-2 text-[10px]">{t.key}:</span>
                               <span className="text-blue-600 dark:text-blue-400 font-bold">{t.value}</span>
                             </span>
                           ))}
                         </div>
                       )}
                       <ReactMarkdown
                         remarkPlugins={[remarkGfm]}
                         components={{
                           a: ({ node, ...props }) => (
                             <a 
                               {...props} 
                               className="text-blue-600 hover:underline" 
                               target="_blank" 
                               rel="noopener noreferrer" 
                             />
                           )
                         }}
                       >
                         {cleanContent}
                       </ReactMarkdown>
                     </>
                   );
                })()}
              </div>
            ) : (
              <div className="bg-gray-50 dark:bg-gray-800 p-6 rounded-lg border border-gray-200 dark:border-gray-700">
                <pre className="whitespace-pre-wrap font-mono text-sm text-gray-800 dark:text-gray-200 leading-relaxed">
                  {content}
                </pre>
              </div>
            )
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-gray-400 dark:text-gray-600">
              <FileCheck className="w-16 h-16 mb-4 opacity-20" />
              <p>Select a source file from the list to view its content.</p>
              <p className="text-sm mt-2 italic text-gray-300 dark:text-gray-700">PDFs will show extracted text.</p>
            </div>
          )}
        </div>
      </div>

      {/* Floating Mobile Toggle Button */}
      {!isDesktop && !showMobileList && (
        <button
          onClick={() => setShowMobileList(true)}
          className="fixed bottom-6 left-6 p-4 bg-gray-900 text-white rounded-full shadow-xl hover:bg-black hover:scale-105 active:scale-95 transition-all z-40 flex items-center justify-center transform"
          title="Back to Sources List"
        >
          <ArrowLeft className="w-6 h-6" />
        </button>
      )}

      {/* Floating Mobile Bulk Mode Button */}
      {!isDesktop && showMobileList && selectedItems.size === 0 && !isBulkMode && (
        <button
          onClick={() => setIsBulkMode(true)}
          className="fixed bottom-6 right-6 p-4 bg-gray-900 text-white rounded-full shadow-xl hover:bg-black hover:scale-105 active:scale-95 transition-all z-40 flex items-center justify-center transform"
          title="Enter Bulk Mode"
        >
          <ListChecks className="w-6 h-6" />
        </button>
      )}

      {/* Floating Mobile Action Menu */}
      {!isDesktop && !showMobileList && selectedSource && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex flex-col items-center">
          {showActionMenu && (
            <div className="flex flex-col items-stretch space-y-3 mb-4 animate-in slide-in-from-bottom-2 fade-in duration-200">
              {selectedItems.size === 0 && (
                <>
                  {!sourcesMetadata[selectedSource]?.ingested && (
                    <button
                      onClick={() => { handleIngest(); setShowActionMenu(false); }}
                      disabled={!!ingesting}
                      className="flex justify-start items-center px-5 py-2 bg-blue-600 text-white rounded-full shadow-md text-sm font-medium hover:bg-blue-700 transition-colors disabled:bg-blue-400"
                    >
                      {ingesting === selectedSource ? (
                        <Loader2 className="w-4 h-4 animate-spin mr-3" />
                      ) : (
                        <Database className="w-4 h-4 mr-3" />
                      )}
                      {ingesting === selectedSource ? 'Ingesting...' : 'Ingest'}
                    </button>
                  )}
                  
                  <button
                    onClick={() => { handleDownload(); setShowActionMenu(false); }}
                    className="flex justify-start items-center px-5 py-2 bg-white text-gray-700 rounded-full shadow-md text-sm font-medium hover:bg-gray-50 transition-colors"
                  >
                    <Download className="w-4 h-4 mr-3" />
                    Download
                  </button>
                  <button
                    onClick={() => { handleDelete(); setShowActionMenu(false); }}
                    disabled={isDeleting}
                    className="flex justify-start items-center px-5 py-2 bg-red-50 text-red-600 rounded-full shadow-md text-sm font-medium hover:bg-red-100 transition-colors disabled:opacity-50"
                  >
                    {isDeleting ? <Loader2 className="w-4 h-4 animate-spin mr-3" /> : <Trash2 className="w-4 h-4 mr-3" />}
                    Archive
                  </button>
                </>
              )}
              {selectedItems.size > 0 && (
                <div className="bg-gray-900/90 backdrop-blur-md p-4 rounded-3xl shadow-2xl border border-white/10 space-y-3">
                  <div className="text-xs font-bold text-gray-400 uppercase tracking-widest text-center mb-1">{selectedItems.size} Selected</div>
                  <button
                    onClick={() => { handleBulkIngest(); setShowActionMenu(false); }}
                    className="w-full flex justify-center items-center py-3 bg-blue-600 text-white rounded-2xl font-bold"
                  >
                    Bulk Ingest
                  </button>
                  <button
                    onClick={() => { handleBulkDownloadSources(); setShowActionMenu(false); }}
                    className="w-full flex justify-center items-center py-3 bg-gray-600 text-white rounded-2xl font-bold"
                  >
                    Bulk Download
                  </button>
                  <button
                    onClick={() => { setShowConfirm(true); setShowActionMenu(false); }}
                    className="w-full flex justify-center items-center py-3 bg-red-600 text-white rounded-2xl font-bold"
                  >
                    Bulk Archive
                  </button>
                </div>
              )}
            </div>
          )}
          
          <button
            onClick={() => setShowActionMenu(!showActionMenu)}
            className={`p-4 rounded-full shadow-xl transition-all transform hover:scale-105 active:scale-95 flex items-center justify-center bg-gray-900 text-white`}
            title="Page Actions"
          >
            {showActionMenu ? <X className="w-6 h-6" /> : <MoreVertical className="w-6 h-6" />}
          </button>
        </div>
      )}

      </div>{/* end inner flex row */}

      <AddSourcesModal
        open={showAddModal}
        onClose={() => setShowAddModal(false)}
        onSourceAdded={(isAsync) => {
          if (isAsync) {
            startPolling(sources.length);
          } else {
            fetchSources();
            fetchSourceIndex();
          }
        }}
      />

      {error && (
        <ErrorToast message={error} onDismiss={() => setError(null)} />
      )}

      {showConfirm && (
        <ConfirmDialog
          message={`Archive ${selectedItems.size} source${selectedItems.size === 1 ? '' : 's'}? This can be undone from the Archive view.`}
          confirmLabel="Archive"
          onConfirm={handleBulkArchive}
          onCancel={() => setShowConfirm(false)}
        />
      )}
    </div>
  );
};

export default SourcesView;

import React, { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import '../wiki-doc.css';
import MDEditor from '@uiw/react-md-editor';
import { FileText, ChevronRight, Loader2, ArrowLeft, ArrowRight, Edit3, Save, X, Trash2, Download, Plus, FilePlus, MoreVertical, MessageSquare, FolderPlus, Pencil, Search, ListChecks, MoveRight, List, Upload, Link2, Tags, Sparkles } from 'lucide-react';

import ChatPanel from './ChatPanel';
import ImportWikiModal from './ImportWikiModal';

import { API_BASE } from '../config';
import { formatPageName } from '../utils/formatPageName';
import ErrorToast from './ErrorToast';
import ConfirmDialog from './ConfirmDialog';
import MoveDialog from './MoveDialog';
import octopusLight from '../assets/octopus-light.png';
import octopusDark from '../assets/octopus-dark.png';

type PageTree = Record<string, string[]>;

type SearchEntry = {
  path: string;
  title: string;
  entity_type: string;
  tags: string[];
  frontmatter: Record<string, unknown>;
  content_preview: string;
};

type SearchIndex = {
  pages: SearchEntry[];
  sources: Array<{
    filename: string;
    display_name: string;
    tags: string[];
    metadata: { ingested: boolean; upload_date: string | null };
  }>;
};

interface WikiViewProps {
  pagesMetadata: Record<string, { read: boolean; read_at: string | null }>;
  onMarkPageRead: (path: string) => void;
}

const WikiView: React.FC<WikiViewProps> = ({ pagesMetadata, onMarkPageRead }) => {
  const [pageTree, setPageTree] = useState<PageTree>({});
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [showImportModal, setShowImportModal] = useState(false);
  const [entityTypes, setEntityTypes] = useState<Record<string, { name: string; description?: string; singular?: string }>>({});
  const [selectedPage, setSelectedPage] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [backlinks, setBacklinks] = useState<string[]>([]);
  const [historyStack, setHistoryStack] = useState<string[]>([]);
  const [forwardStack, setForwardStack] = useState<string[]>([]);
  
  // Editing states
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editedContent, setEditedContent] = useState<string>('');
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isSystemPage, setIsSystemPage] = useState<boolean>(false);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);
  const [isCreating, setIsCreating] = useState<boolean>(false);
  const [showNewPageMenu, setShowNewPageMenu] = useState(false);

  // Resizable sidebar state
  const [sidebarWidth, setSidebarWidth] = useState<number>(256);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);

  // Track pagesMetadata keys to detect newly ingested pages
  const seenPageKeysRef = useRef<Set<string>>(new Set());

  // Mobile/Tablet responsive states
  const [isDesktop, setIsDesktop] = useState(window.innerWidth >= 1024);
  const [showMobileList, setShowMobileList] = useState(true);
  const [showActionMenu, setShowActionMenu] = useState(false);
  const [showChat, setShowChat] = useState<boolean>(false);
  const [chatWidth, setChatWidth] = useState<number>(350);
  const dragChatRef = useRef<{ startX: number; startWidth: number } | null>(null);

  const [loading, setLoading] = useState<boolean>(true);
  const [contentLoading, setContentLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [searchIndex, setSearchIndex] = useState<SearchIndex | null>(null);
  const [tagFilter, setTagFilter] = useState<string[]>([]);
  const [suggestedTags, setSuggestedTags] = useState<string[]>([]);

  // Tag management state
  const [pageTags, setPageTags] = useState<string[]>([]);
  const [tagVocabulary, setTagVocabulary] = useState<string[]>([]);
  const [addingTag, setAddingTag] = useState(false);
  const [newTagInput, setNewTagInput] = useState('');
  const [isBulkMode, setIsBulkMode] = useState(false);

  // Folder management state
  const [showNewFolderDialog, setShowNewFolderDialog] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [newFolderDisplayName, setNewFolderDisplayName] = useState('');
  const [newFolderDescription, setNewFolderDescription] = useState('');
  const [renamingFolder, setRenamingFolder] = useState<string | null>(null);
  const [renameFolderValue, setRenameFolderValue] = useState('');
  const [renamingPage, setRenamingPage] = useState<string | null>(null);
  const [renamePageValue, setRenamePageValue] = useState('');
  const [showMobileRenameInput, setShowMobileRenameInput] = useState(false);
  const [showMoveDialog, setShowMoveDialog] = useState(false);
  const [selectedPages, setSelectedPages] = useState<Set<string>>(new Set());
  const [hoveredPage, setHoveredPage] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [showBulkMoveDialog, setShowBulkMoveDialog] = useState(false);

  // Frontmatter inline editing
  const [fieldSchema, setFieldSchema] = useState<Record<string, string[]>>({});
  const [savingField, setSavingField] = useState<string | null>(null);
  const [savedField, setSavedField] = useState<string | null>(null);

  const fetchSearchIndex = async () => {
    try {
      const res = await fetch(`${API_BASE}/search/index`);
      if (!res.ok) return;
      const data: SearchIndex = await res.json();
      setSearchIndex(data);
    } catch {
      // search unavailable — silently degrade
    }
  };

  const fetchFieldSchema = async (pagePath: string) => {
    const entityType = pagePath.split('/')[0];
    if (!entityType || entityType.startsWith('_')) {
      setFieldSchema({});
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/entity-types/${entityType}/field-schema`);
      if (!res.ok) { setFieldSchema({}); return; }
      const data = await res.json();
      setFieldSchema(data.schema ?? {});
    } catch {
      setFieldSchema({});
    }
  };

  const fetchTagVocabulary = async () => {
    try {
      const res = await fetch(`${API_BASE}/tags`);
      if (!res.ok) return;
      const data: Record<string, number> = await res.json();
      setTagVocabulary(Object.keys(data).sort());
    } catch {}
  };

  const fetchEntityTypes = async () => {
    try {
      const response = await fetch(`${API_BASE}/entity-types`);
      if (!response.ok) throw new Error('Failed to fetch entity types');
      const data = await response.json();
      setEntityTypes(data);
      setExpandedSections(prev => {
        const next = { ...prev };
        for (const key of Object.keys(data)) {
          if (!(key in next)) next[key] = false;
        }
        return next;
      });
    } catch (err: any) {
      setError(err.message);
    }
  };

  useEffect(() => {
    fetchEntityTypes();
    fetchPages();
    fetchSearchIndex();
    fetchTagVocabulary();

    // Track window resizes for responsive layout
    const handleResize = () => setIsDesktop(window.innerWidth >= 1024);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    const currentKeys = Object.keys(pagesMetadata);
    if (seenPageKeysRef.current.size === 0) {
      // First time we see pages — record them, don't trigger a redundant fetch
      seenPageKeysRef.current = new Set(currentKeys);
      return;
    }
    const hasNew = currentKeys.some(k => !seenPageKeysRef.current.has(k));
    if (hasNew) {
      seenPageKeysRef.current = new Set(currentKeys);
      fetchPages();
    }
  }, [pagesMetadata]);

  const togglePageSelection = (path: string) => {
    setSelectedPages(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  };

  const selectAllPages = () => {
    // Select based on current search results if searching, otherwise all pages
    if (searchResults) {
      setSelectedPages(new Set(searchResults.map(r => r.path)));
    } else {
      const allPaths: string[] = Object.values(pageTree).flat();
      setSelectedPages(new Set(allPaths));
    }
  };

  const clearPageSelection = () => { setSelectedPages(new Set()); setIsBulkMode(false); };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') clearPageSelection();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleMouseDown = (e: React.MouseEvent) => {
    dragRef.current = { startX: e.clientX, startWidth: sidebarWidth };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  const handleChatMouseDown = (e: React.MouseEvent) => {
    dragChatRef.current = { startX: e.clientX, startWidth: chatWidth };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (dragRef.current) {
      const { startX, startWidth } = dragRef.current;
      const newWidth = Math.min(Math.max(200, startWidth + (e.clientX - startX)), 800);
      setSidebarWidth(newWidth);
    }
    if (dragChatRef.current) {
      const { startX, startWidth } = dragChatRef.current;
      const newWidth = Math.min(Math.max(250, startWidth - (e.clientX - startX)), 800);
      setChatWidth(newWidth);
    }
  }, []);

  const handleMouseUp = useCallback(() => {
    if (dragRef.current) dragRef.current = null;
    if (dragChatRef.current) dragChatRef.current = null;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }, []);

  useEffect(() => {
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  const fetchPages = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE}/pages`);
      if (!response.ok) throw new Error('Failed to fetch pages');
      const data: PageTree = await response.json();
      setPageTree(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const fetchPageContent = async (filename: string, addToHistory: boolean = true, skipDirtyCheck: boolean = false) => {
    if (!skipDirtyCheck && isEditing && editedContent !== content) {
      if (!window.confirm('You have unsaved changes. Discard them and navigate away?')) return;
    }

    try {
      setContentLoading(true);
      setIsEditing(false);
      setIsSystemPage(false);

      // History management
      if (addToHistory && selectedPage && selectedPage !== filename) {
        setHistoryStack(prev => [...prev, selectedPage]);
        setForwardStack([]);
      }

      setSelectedPage(filename);
      onMarkPageRead(filename);
      fetchFieldSchema(filename);

      // Fetch content and backlinks in parallel
      const [contentRes, backlinksRes] = await Promise.all([
        fetch(`${API_BASE}/pages/${encodeURIComponent(filename)}`),
        fetch(`${API_BASE}/pages/${encodeURIComponent(filename)}/backlinks`)
      ]);

      if (!contentRes.ok) throw new Error('Failed to fetch page content');
      
      const contentData = await contentRes.json();
      const backlinksData = backlinksRes.ok ? await backlinksRes.json() : [];

      setContent(contentData.content);
      setEditedContent(contentData.content);
      setBacklinks(backlinksData);

      // Parse tags from frontmatter
      const tagsMatch = contentData.content.match(/^tags:\s*\n((?:\s*-\s+\S+\n?)*)/m);
      if (tagsMatch) {
        const tags = tagsMatch[1]
          .split('\n')
          .map((l: string) => l.replace(/^\s*-\s+/, '').trim())
          .filter(Boolean);
        setPageTags(tags);
      } else {
        const inlineMatch = contentData.content.match(/^tags:\s*\[([^\]]*)\]/m);
        if (inlineMatch) {
          setPageTags(inlineMatch[1].split(',').map((t: string) => t.trim().replace(/['"]/g, '')).filter(Boolean));
        } else {
          setPageTags([]);
        }
      }
      setSuggestedTags([]);

      const systemMatch = /^system:\s*true\s*$/m.test(contentData.content);
      setIsSystemPage(systemMatch);

      // Auto-switch away from list view on small screens
      setShowMobileList(false);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setContentLoading(false);
    }
  };

  const handleSave = async () => {
    if (!selectedPage) return;
    try {
      setIsSaving(true);
      const response = await fetch(`${API_BASE}/pages/${encodeURIComponent(selectedPage)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: editedContent }),
      });

      if (!response.ok) throw new Error('Failed to save page');

      const saveData = await response.json();
      if (saveData.suggested_tags && saveData.suggested_tags.length > 0) {
        setSuggestedTags(saveData.suggested_tags);
      }

      setContent(editedContent);
      setIsEditing(false);

      if (saveData.new_filename) {
        // File was renamed from Untitled — navigate to the new path
        await fetchPages();
        setSelectedPage(saveData.new_filename);
        await fetchPageContent(saveData.new_filename, true, true);
      } else {
        fetchPages();
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsSaving(false);
    }
  };

  const handleNewPage = async (entityType: string) => {
    try {
      setIsCreating(true);
      setShowNewPageMenu(false);
      const response = await fetch(`${API_BASE}/pages?entity_type=${entityType}`, { method: 'POST' });
      if (!response.ok) throw new Error('Failed to create new page');
      const data = await response.json();
      await fetchPages();
      await fetchPageContent(data.filename);
      setIsEditing(true); // Open in edit mode immediately
      setShowMobileList(false); // Move focus to content view on mobile
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsCreating(false);
    }
  };

  const handleAddTag = async (tag: string) => {
    const trimmed = tag.toLowerCase().trim();
    if (!trimmed || pageTags.includes(trimmed) || !selectedPage) return;
    const newTags = [...pageTags, trimmed];
    setPageTags(newTags);
    setAddingTag(false);
    setNewTagInput('');
    try {
      await fetch(`${API_BASE}/pages/${encodeURIComponent(selectedPage)}/tags`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags: newTags }),
      });
      fetchSearchIndex();
      fetchTagVocabulary();
    } catch { setPageTags(pageTags); }
  };

  const handleRemoveTag = async (tag: string) => {
    if (!selectedPage) return;
    const newTags = pageTags.filter(t => t !== tag);
    setPageTags(newTags);
    try {
      await fetch(`${API_BASE}/pages/${encodeURIComponent(selectedPage)}/tags`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tags: newTags }),
      });
      fetchSearchIndex();
    } catch { setPageTags(pageTags); }
  };

  const handleAcceptSuggestedTag = async (tag: string) => {
    setSuggestedTags(prev => prev.filter(t => t !== tag));
    await handleAddTag(tag);
  };

  const handleDelete = async () => {
    if (!selectedPage) return;
    if (!window.confirm(`Move '${formatPageName(selectedPage)}' to archive?`)) return;

    try {
      setIsDeleting(true);
      const response = await fetch(`${API_BASE}/pages/${encodeURIComponent(selectedPage)}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error('Failed to delete page');

      setSelectedPage(null);
      setContent(null);
      setIsSystemPage(false);
      fetchPages();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleBulkArchivePages = async () => {
    setShowConfirm(false);
    try {
      const res = await fetch(`${API_BASE}/pages/bulk`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths: Array.from(selectedPages) }),
      });
      const data = await res.json();
      if (data.errors?.length) {
        setError(`Failed to archive: ${data.errors.join(', ')}`);
      }
      // If currently selected page was archived, clear it
      if (selectedPage && selectedPages.has(selectedPage)) {
        setSelectedPage(null);
        setContent(null);
        setIsSystemPage(false);
      }
      clearPageSelection();
      fetchPages();
    } catch {
      setError('Failed to archive selected pages');
    }
  };

  const handleBulkMove = async (destination: string) => {
    setShowBulkMoveDialog(false);
    try {
      const res = await fetch(`${API_BASE}/pages/bulk-move`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths: Array.from(selectedPages), destination }),
      });
      const data = await res.json();
      const movedCount = data.moved?.length ?? 0;
      const linkCount = Object.values(data.links_rewritten ?? {}).reduce((a: number, b) => a + (b as number), 0);
      if (data.errors?.length) {
        setError(`Moved ${movedCount} page(s). Failed: ${data.errors.map((e: { path: string }) => e.path).join(', ')}`);
      } else if (movedCount > 0) {
        const linkMsg = linkCount > 0 ? ` ${linkCount} wikilink(s) updated.` : '';
        setError(`Moved ${movedCount} page(s) to ${destination}.${linkMsg}`);
      }
      clearPageSelection();
      fetchPages();
    } catch {
      setError('Failed to move selected pages');
    }
  };

  const handleBulkDownloadPages = async () => {
    try {
      const res = await fetch(`${API_BASE}/pages/bulk-download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths: Array.from(selectedPages) }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setError(err.detail ?? 'Failed to download pages');
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'pages-export.zip';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      setError('Failed to download selected pages');
    }
  };

  const handleDownload = () => {
    if (!selectedPage) return;
    window.open(`${API_BASE}/pages/${encodeURIComponent(selectedPage)}/download`);
  };

  const handleCreateFolder = async () => {
    if (!newFolderName.trim() || !newFolderDisplayName.trim()) return;
    try {
      const response = await fetch(`${API_BASE}/folders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newFolderName.trim().toLowerCase().replace(/\s+/g, '-'),
          display_name: newFolderDisplayName.trim(),
          description: newFolderDescription.trim(),
        }),
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to create folder');
      }
      setShowNewFolderDialog(false);
      setNewFolderName('');
      setNewFolderDisplayName('');
      setNewFolderDescription('');
      await fetchEntityTypes();
      await fetchPages();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleDeleteFolder = async (folderName: string) => {
    if (!window.confirm(`Delete the "${folderName}" folder? It must be empty.`)) return;
    try {
      const response = await fetch(`${API_BASE}/folders/${folderName}`, { method: 'DELETE' });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to delete folder');
      }
      setSelectedFolder(null);
      await fetchEntityTypes();
      await fetchPages();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleRenameFolder = async (oldName: string) => {
    if (!renameFolderValue.trim()) return;
    const newName = renameFolderValue.trim().toLowerCase().replace(/\s+/g, '-');
    try {
      const response = await fetch(`${API_BASE}/folders/${oldName}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_name: newName }),
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to rename folder');
      }
      setRenamingFolder(null);
      setRenameFolderValue('');
      // Update selectedFolder if the renamed folder was selected
      if (selectedFolder === oldName) {
        setSelectedFolder(newName);
      } else {
        // Clear selectedFolder for safety since the folder structure changed
        setSelectedFolder(null);
      }
      // Update selectedPage path if it was in the renamed folder
      if (selectedPage?.startsWith(oldName + '/')) {
        setSelectedPage(selectedPage.replace(oldName + '/', newName + '/'));
      }
      await fetchEntityTypes();
      await fetchPages();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleRenamePage = async (pagePath: string) => {
    const newName = renamePageValue.trim();
    if (!newName) { setRenamingPage(null); setShowMobileRenameInput(false); return; }
    try {
      const response = await fetch(`${API_BASE}/pages/${encodeURIComponent(pagePath)}/rename`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_name: newName }),
      });
      if (!response.ok) throw new Error('Failed to rename page');
      const data = await response.json();
      setRenamingPage(null);
      setRenamePageValue('');
      setShowMobileRenameInput(false);
      setShowActionMenu(false);
      await fetchPages();
      if (selectedPage === pagePath) {
        setSelectedPage(data.new_path);
        await fetchPageContent(data.new_path);
      }
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleMovePage = async (targetFolder: string) => {
    if (!selectedPage) return;
    try {
      const response = await fetch(`${API_BASE}/pages/${encodeURIComponent(selectedPage)}/move`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_folder: targetFolder }),
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to move page');
      }
      const data = await response.json();
      setSelectedPage(data.new_path);
      setShowMoveDialog(false);
      await fetchPages();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleBack = () => {
    if (historyStack.length === 0) return;
    const previous = historyStack[historyStack.length - 1];
    setHistoryStack(prev => prev.slice(0, -1));
    if (selectedPage) setForwardStack(prev => [selectedPage, ...prev]);
    fetchPageContent(previous, false);
  };

  const handleForward = () => {
    if (forwardStack.length === 0) return;
    const next = forwardStack[0];
    setForwardStack(prev => prev.slice(1));
    if (selectedPage) setHistoryStack(prev => [...prev, selectedPage]);
    fetchPageContent(next, false);
  };

  const processWikiLinks = (text: string, tree: PageTree) => {
    return text.replace(/\[\[(.*?)\]\]/g, (_match, p1) => {
      const trimmed = p1.trim();

      // If it already contains a slash, it's a full path reference
      if (trimmed.includes('/')) {
        return `[${trimmed.split('/').pop()?.replace(/-/g, ' ')}](#${trimmed.replace('/', '__')})`;
      }

      // Otherwise, look up which subdirectory contains this page
      const slug = trimmed.toLowerCase().replace(/\s+/g, '-');
      for (const [_section, pages] of Object.entries(tree)) {
        const found = pages.find(p => p.endsWith(`/${slug}.md`));
        if (found) {
          const ref = found.replace('/', '__').replace('.md', '');
          return `[${trimmed}](#${ref})`;
        }
      }

      // Fallback: render as plain anchor
      return `[${trimmed}](#${slug})`;
    });
  };

  const resolvePageLink = (name: string): string | null => {
    const slug = name.toLowerCase().replace(/\s+/g, '-');
    for (const [, pages] of Object.entries(pageTree)) {
      const found = pages.find(p => p.endsWith(`/${slug}.md`));
      if (found) return found;
    }
    return null;
  };

  const renderWikiToken = (text: string, key: string | number): React.ReactNode => {
    const wikiMatch = text.match(/^\[\[(.*?)\]\]$/);
    const name = wikiMatch ? wikiMatch[1].trim() : text.trim();
    let pagePath: string;
    let displayText: string;
    if (name.includes('/')) {
      displayText = name.split('/').pop()?.replace(/-/g, ' ') || name;
      pagePath = name + '.md';
    } else {
      displayText = name;
      pagePath = resolvePageLink(name) ?? (name.toLowerCase().replace(/\s+/g, '-') + '.md');
    }
    const path = pagePath;
    const isLinked = wikiMatch || resolvePageLink(name) !== null;
    if (isLinked) {
      return (
        <button key={key} onClick={() => fetchPageContent(path)}
          className="text-blue-600 dark:text-blue-400 hover:underline cursor-pointer font-medium">
          {displayText}
        </button>
      );
    }
    return <span key={key}>{displayText}</span>;
  };

  const patchFrontmatterField = async (field: string, value: string) => {
    if (!selectedPage) return;
    setSavingField(field);
    try {
      await fetch(`${API_BASE}/pages/${encodeURIComponent(selectedPage)}/frontmatter`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ field, value }),
      });
      setContent(prev => {
        if (!prev) return prev;
        return prev.replace(
          new RegExp(`^(${field}\\s*:).*$`, 'm'),
          `$1 ${value}`
        );
      });
      setSavedField(field);
      setTimeout(() => setSavedField(null), 1500);
    } catch {
      // silently fail — raw editor still available
    } finally {
      setSavingField(null);
    }
  };

  // Decode a raw YAML scalar string: strip outer quotes and unescape
  // single-quote sequences ('') so [[L''Oreal]] → [[L'Oreal]].
  const decodeYamlScalar = (raw: string): string => {
    const trimmed = raw.trim();
    if (trimmed.startsWith("'") && trimmed.endsWith("'") && trimmed.length >= 2) {
      return trimmed.slice(1, -1).replace(/''/g, "'");
    }
    if (trimmed.startsWith('"') && trimmed.endsWith('"') && trimmed.length >= 2) {
      return trimmed.slice(1, -1);
    }
    return trimmed;
  };

  const renderFrontmatterValue = (raw: string): React.ReactNode => {
    const value = decodeYamlScalar(raw);

    // Handle inline array values: ["a", "b"] or [] — but not [[wikilinks]]
    if (value.startsWith('[') && !value.startsWith('[[') && value.endsWith(']')) {
      const inner = value.slice(1, -1).trim();
      if (!inner) return <span className="text-gray-400 dark:text-gray-500 italic text-xs">none</span>;
      const items = (inner.match(/"[^"]*?"|'[^']*?'|\[\[.*?\]\]|[^,]+/g) ?? [])
        .map(s => s.replace(/^["'\s]+|["'\s]+$/g, '').trim())
        .filter(Boolean);
      return (
        <span className="flex flex-wrap gap-1">
          {items.map((item, i) => (
            <span key={i} className="inline-flex items-center px-2 py-0.5 rounded-full bg-blue-50 dark:bg-blue-900/30 border border-blue-100 dark:border-blue-800 text-xs">
              {renderWikiToken(item, i)}
            </span>
          ))}
        </span>
      );
    }

    // Handle scalar values with optional [[wikilinks]] inline
    const parts: React.ReactNode[] = [];
    const regex = /\[\[(.*?)\]\]/g;
    let lastIndex = 0;
    let match;
    while ((match = regex.exec(value)) !== null) {
      if (match.index > lastIndex) parts.push(value.slice(lastIndex, match.index));
      parts.push(renderWikiToken(match[0], match.index));
      lastIndex = match.index + match[0].length;
    }
    if (lastIndex < value.length) parts.push(value.slice(lastIndex));
    return parts.length ? <>{parts}</> : value;
  };

  const READ_ONLY_FM_FIELDS = new Set(['type', 'name']);

  const EnumFrontmatterValue: React.FC<{
    fieldKey: string;
    value: string;
    options: string[];
    indicator: React.ReactNode;
    isSaving: boolean;
    onSave: (field: string, value: string) => Promise<void>;
  }> = ({ fieldKey, value, options, indicator, isSaving, onSave }) => {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLSpanElement>(null);

    useEffect(() => {
      if (!open) return;
      const handler = (e: MouseEvent) => {
        if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
      };
      document.addEventListener('mousedown', handler);
      return () => document.removeEventListener('mousedown', handler);
    }, [open]);

    const select = (opt: string) => {
      setOpen(false);
      if (opt !== value) onSave(fieldKey, opt);
    };

    return (
      <span ref={ref} className="inline-flex items-center relative">
        <button
          disabled={isSaving}
          onClick={() => setOpen(o => !o)}
          className="text-blue-600 dark:text-blue-400 font-bold text-xs cursor-pointer hover:underline focus:underline outline-none bg-transparent border-none p-0"
          style={{ fontFamily: 'inherit' }}
        >
          {value || '—'}
        </button>
        {indicator}
        {open && (
          <span className="absolute left-0 top-full mt-1 z-50 min-w-[120px] rounded shadow-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-900 py-1 flex flex-col">
            <button
              onClick={() => select('')}
              className="text-left px-3 py-1 text-xs text-gray-400 dark:text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              —
            </button>
            {options.map(opt => (
              <button
                key={opt}
                onClick={() => select(opt)}
                className={`text-left px-3 py-1 text-xs hover:bg-gray-100 dark:hover:bg-gray-800 ${opt === value ? 'text-blue-600 dark:text-blue-400 font-bold' : 'text-gray-800 dark:text-gray-100'}`}
              >
                {opt}
              </button>
            ))}
          </span>
        )}
      </span>
    );
  };

  const FrontmatterValue: React.FC<{ fieldKey: string; raw: string }> = ({ fieldKey, raw }) => {
    const value = decodeYamlScalar(raw);
    const isSaving = savingField === fieldKey;
    const isSaved = savedField === fieldKey;
    const isReadOnly = READ_ONLY_FM_FIELDS.has(fieldKey);

    if (value.startsWith('[') && !value.startsWith('[[')) {
      return <span className="text-blue-600 dark:text-blue-400 font-bold">{renderFrontmatterValue(raw)}</span>;
    }

    if (isReadOnly) {
      return <span className="text-blue-600 dark:text-blue-400 font-bold">{renderFrontmatterValue(raw)}</span>;
    }

    const indicator = isSaving
      ? <span className="ml-1 text-gray-400 dark:text-gray-500 text-[9px]">…</span>
      : isSaved
      ? <span className="ml-1 text-green-500 text-[9px]">✓</span>
      : null;

    if (fieldSchema[fieldKey]) {
      return <EnumFrontmatterValue fieldKey={fieldKey} value={value} options={fieldSchema[fieldKey]} indicator={indicator} onSave={patchFrontmatterField} isSaving={isSaving} />;
    }

    return <TextFrontmatterValue fieldKey={fieldKey} value={value} indicator={indicator} onSave={patchFrontmatterField} />;
  };

  const TextFrontmatterValue: React.FC<{
    fieldKey: string;
    value: string;
    indicator: React.ReactNode;
    onSave: (field: string, value: string) => Promise<void>;
  }> = ({ fieldKey, value, indicator, onSave }) => {
    const [editing, setEditing] = useState(false);
    const [draft, setDraft] = useState(value);
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => { if (editing) inputRef.current?.focus(); }, [editing]);

    const commit = () => {
      setEditing(false);
      if (draft !== value) onSave(fieldKey, draft);
    };

    if (!editing) {
      return (
        <span className="inline-flex items-center">
          <span
            className="text-blue-600 dark:text-blue-400 font-bold cursor-text hover:underline"
            onClick={() => { setDraft(value); setEditing(true); }}
          >
            {value || <span className="text-gray-300 dark:text-gray-600 italic font-normal">—</span>}
          </span>
          {indicator}
        </span>
      );
    }

    return (
      <input
        ref={inputRef}
        value={draft}
        onChange={e => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={e => {
          if (e.key === 'Enter') commit();
          if (e.key === 'Escape') { setDraft(value); setEditing(false); }
        }}
        className="text-blue-600 dark:text-blue-400 font-bold text-xs bg-transparent border-b border-blue-400 dark:border-blue-600 outline-none min-w-[4rem]"
        style={{ fontFamily: 'inherit' }}
      />
    );
  };

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

  const searchResults: SearchEntry[] | null = (() => {
    if (!searchIndex || !searchQuery.trim()) return null;
    const q = searchQuery.toLowerCase();
    return searchIndex.pages.filter(page => {
      const matchesQuery =
        page.title.toLowerCase().includes(q) ||
        page.content_preview.toLowerCase().includes(q) ||
        page.tags.some(t => t.toLowerCase().includes(q)) ||
        Object.values(page.frontmatter).some(v => String(v).toLowerCase().includes(q));
      const matchesTags =
        tagFilter.length === 0 || tagFilter.every(t => page.tags.includes(t));
      return matchesQuery && matchesTags;
    });
  })();

  const resultTags: string[] = (() => {
    if (!searchResults) return [];
    const all = new Set<string>();
    searchResults.forEach(r => r.tags.forEach(t => all.add(t)));
    return Array.from(all).sort();
  })();

  const totalPageCount = Object.values(pageTree).reduce((sum, pages) => sum + pages.length, 0);
  const entityTypeCount = Object.keys(entityTypes).length;

  const sectionStats: Array<{ section: string; name: string; total: number; unread: number }> =
    Object.entries(entityTypes).map(([section, typeData]) => {
      const sectionPages = pageTree[section] || [];
      const unread = sectionPages.filter(p => pagesMetadata[p]?.read === false).length;
      return { section, name: typeData.name || section, total: sectionPages.length, unread };
    }).sort((a, b) => b.total - a.total);

  const totalUnreadCount = sectionStats.reduce((sum, s) => sum + s.unread, 0);

  const highlightMatch = (text: string, query: string): React.ReactNode => {
    if (!query.trim()) return text;
    const idx = text.toLowerCase().indexOf(query.toLowerCase());
    if (idx === -1) return text;
    return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-yellow-100 text-yellow-800 rounded-sm px-0.5">{text.slice(idx, idx + query.length)}</mark>
      {text.slice(idx + query.length)}
    </>
  );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="animate-spin mr-2" /> Loading Wiki...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full relative">
      {/* Search bar — full width above sidebar+content */}
      <div className="border-b border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 px-4 py-2 flex items-center gap-3">
        <Search className="w-4 h-4 text-gray-400 shrink-0" />
        <input
          type="text"
          value={searchQuery}
          onChange={e => { setSearchQuery(e.target.value); setTagFilter([]); }}
          placeholder="Search wiki pages…"
          className="flex-1 bg-transparent text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 outline-none"
        />
        {searchQuery && (
          <button onClick={() => { setSearchQuery(''); setTagFilter([]); }}
                  className="text-gray-500 hover:text-gray-300">
            <X className="w-4 h-4" />
          </button>
        )}
        {searchIndex && (
          <span className="text-xs text-gray-500 shrink-0">
            {searchResults ? `${searchResults.length} result${searchResults.length !== 1 ? 's' : ''}` : ''}
          </span>
        )}
        {!searchIndex && <span className="text-xs text-gray-500">Search unavailable</span>}
      </div>
      <div className="flex flex-1 min-h-0 relative">
      {/* Sidebar - Page List */}
      <div 
        className={`border-r dark:border-gray-800 bg-white dark:bg-gray-900 flex flex-col flex-shrink-0 ${!isDesktop && !showMobileList ? 'hidden' : 'flex'} ${!isDesktop ? 'w-full' : ''}`}
        style={isDesktop ? { width: sidebarWidth } : undefined}
      >
        <div className="p-4 border-b border-gray-50 dark:border-gray-800 flex-shrink-0">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Pages</h2>
            <div className="flex items-center space-x-1">
              <button
                onClick={() => setShowNewFolderDialog(true)}
                className="p-1.5 bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-400 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                title="New Folder"
              >
                <FolderPlus className="w-4 h-4" />
              </button>
              <button
                onClick={() => setShowImportModal(true)}
                disabled={!selectedFolder}
                className="p-1.5 bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-400 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                title={selectedFolder ? `Import markdown files into ${selectedFolder}` : 'Select a folder first'}
              >
                <Upload className="w-4 h-4" />
              </button>
              <div className="relative">
                <button
                  onClick={() => setShowNewPageMenu(prev => !prev)}
                  disabled={isCreating}
                  className="p-1.5 bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors disabled:opacity-50"
                  title="New Page"
                >
                  {isCreating ? <Loader2 className="w-4 h-4 animate-spin" /> : <FilePlus className="w-4 h-4" />}
                </button>
                {showNewPageMenu && (
                  <div className="absolute right-0 mt-1 w-44 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-100 dark:border-gray-700 z-20 overflow-hidden">
                    {Object.entries(entityTypes).map(([type, data]) => (
                      <button
                        key={type}
                        onClick={() => handleNewPage(type)}
                        className="w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-blue-50 dark:hover:bg-blue-900/50 hover:text-blue-700 dark:hover:text-blue-300 transition-colors"
                      >
                        {data.name || type}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Bulk Action Toolbar - Now Sticky at Top */}
        {(selectedPages.size > 0 || isBulkMode) && (
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-gray-100 rounded-xl p-3 mb-2 shadow-sm animate-in slide-in-from-top-2 duration-300 mx-4">
            <div className="flex items-center justify-between mb-3 px-1">
              <span className="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase tracking-widest">{selectedPages.size} Selected</span>
              <button 
                onClick={clearPageSelection} 
                className="text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full"
                title="Clear selection"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex flex-col gap-2">
              <button
                onClick={selectAllPages}
                className="w-full text-[10px] py-1 bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-400 rounded hover:bg-gray-100 dark:hover:bg-gray-600 transition-all font-medium uppercase tracking-tight"
              >
                Select {searchResults ? 'matching' : 'all'}
              </button>
              <div className="grid grid-cols-3 gap-2">
                <button
                  onClick={() => setShowBulkMoveDialog(true)}
                  className="flex items-center justify-center gap-2 text-xs py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 shadow-sm transition-all font-bold"
                >
                  <MoveRight className="w-3.5 h-3.5" />
                  Move
                </button>
                <button
                  onClick={handleBulkDownloadPages}
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
            {/* Tag filter row */}
            {resultTags.length > 0 && (
              <div className="flex flex-wrap gap-1 px-3 py-2 border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/50">
                <span className="text-xs text-gray-500 dark:text-gray-400 self-center mr-1">Filter:</span>
                {resultTags.map(tag => (
                  <button
                    key={tag}
                    onClick={() =>
                      setTagFilter(prev =>
                        prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]
                      )
                    }
                    className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                      tagFilter.includes(tag)
                        ? 'bg-blue-600 border-blue-500 text-white'
                        : 'bg-gray-100 dark:bg-gray-700 border-gray-200 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:border-gray-300 dark:hover:border-gray-500'
                    }`}
                  >
                    {tagFilter.includes(tag) ? `${tag} ×` : tag}
                  </button>
                ))}
              </div>
            )}
            {/* Results list */}
            <div className="divide-y divide-gray-50/50 dark:divide-gray-800/50">
              {searchResults.length === 0 ? (
                <p className="text-sm text-gray-500 dark:text-gray-400 p-4">No pages match.</p>
              ) : (
                searchResults.map(entry => (
                  <div 
                    key={entry.path}
                    className="group flex items-center px-4 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors border-b border-gray-50 dark:border-gray-800"
                    onMouseEnter={() => setHoveredPage(entry.path)}
                    onMouseLeave={() => setHoveredPage(null)}
                  >
                    <div className="w-6 shrink-0 flex justify-start items-start pt-3">
                      {(hoveredPage === entry.path || selectedPages.size > 0 || isBulkMode) && (
                        <input
                          type="checkbox"
                          checked={selectedPages.has(entry.path)}
                          onChange={() => togglePageSelection(entry.path)}
                          onClick={e => e.stopPropagation()}
                          className="w-4 h-4 accent-blue-600 cursor-pointer shadow-sm hover:scale-110 transition-transform"
                        />
                      )}
                    </div>
                    <button
                      onClick={() => { fetchPageContent(entry.path); setSearchQuery(''); setTagFilter([]); }}
                      className="flex-1 text-left py-3 min-w-0 pr-2"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-bold text-gray-900 dark:text-gray-100 leading-tight truncate mr-2">
                          {highlightMatch(entry.title, searchQuery)}
                        </span>
                        <span className="text-[10px] bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 px-1.5 py-0.5 rounded uppercase font-bold tracking-wider shrink-0">{entry.entity_type}</span>
                      </div>
                      {entry.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mb-1.5">
                          {entry.tags.map(t => (
                            <span key={t} className="text-[10px] px-2.5 py-1 rounded-full bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 border border-blue-100 dark:border-blue-800 font-medium whitespace-nowrap">
                              {t}
                            </span>
                          ))}
                        </div>
                      )}
                      <p className="text-xs text-gray-400 dark:text-gray-500 line-clamp-2 leading-relaxed">
                        {highlightMatch(entry.content_preview, searchQuery)}
                      </p>
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        ) : (
          <>
        {/* Collapsible tree */}
        {Object.keys(entityTypes).length === 0 ? (
          <p className="text-gray-500 text-sm">No pages found. Ingest some data first!</p>
        ) : (
          <div className="space-y-1">
            <button
              onClick={() => fetchPageContent('_meta/index.md')}
              className={`w-full text-left px-2 py-2 rounded-lg text-sm transition-colors flex items-center gap-2 ${
                selectedPage === '_meta/index.md'
                  ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-bold'
                  : 'hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400'
              }`}
            >
              <List className="w-3.5 h-3.5 shrink-0" />
              <span className="text-xs font-semibold uppercase tracking-wider">Index</span>
            </button>
            {Object.entries(entityTypes).map(([section, typeData]) => {
              const sectionPages = pageTree[section] || [];
              const unreadCount = sectionPages.filter(
                p => pagesMetadata[p]?.read === false
              ).length;
              return (
                <div key={section}>
                  <div className="flex items-center group">
                    <button
                      onClick={() => { toggleSection(section); setSelectedFolder(section) }}
                      className={`flex-1 text-left px-2 py-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wider rounded-md transition-colors hover:bg-gray-50 dark:hover:bg-gray-800 ${
                        selectedFolder === section
                          ? 'text-blue-600 dark:text-blue-400'
                          : 'text-gray-400 dark:text-gray-500'
                      }`}
                    >
                      <span className="flex items-center gap-1.5">
                        {typeData.name || section}
                        {unreadCount > 0 && (
                          <span className="px-1.5 py-0.5 rounded-full text-xs font-medium bg-blue-500 text-white leading-none">
                            {unreadCount}
                          </span>
                        )}
                      </span>
                      <ChevronRight className={`w-3 h-3 transition-transform duration-150 ${expandedSections[section] ? 'rotate-90' : ''}`} />
                    </button>
                    <div className="hidden group-hover:flex items-center space-x-0.5 mr-1">
                      <button
                        onClick={() => { setRenamingFolder(section); setRenameFolderValue(section); }}
                        className="p-0.5 text-gray-300 hover:text-gray-500 rounded"
                        title="Rename folder"
                      >
                        <Pencil className="w-3 h-3" />
                      </button>
                      <button
                        onClick={() => handleDeleteFolder(section)}
                        className="p-0.5 text-gray-300 hover:text-red-500 rounded"
                        title="Delete folder"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  </div>

                  {/* Inline rename input */}
                  {renamingFolder === section && (
                    <div className="flex items-center px-2 py-1 space-x-1">
                      <input
                        autoFocus
                        value={renameFolderValue}
                        onChange={e => setRenameFolderValue(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter') handleRenameFolder(section);
                          if (e.key === 'Escape') setRenamingFolder(null);
                        }}
                        className="flex-1 text-xs border dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded px-2 py-1"
                      />
                      <button onClick={() => handleRenameFolder(section)} className="text-xs text-blue-600">Save</button>
                      <button onClick={() => setRenamingFolder(null)} className="text-xs text-gray-400">Cancel</button>
                    </div>
                  )}

                  {expandedSections[section] && sectionPages.length > 0 && (
                    <ul className="ml-1 space-y-0.5 mb-1">
                      {sectionPages.map(pagePath => (
                        <li
                          key={pagePath}
                          className="relative group flex flex-col"
                          onMouseEnter={() => setHoveredPage(pagePath)}
                          onMouseLeave={() => setHoveredPage(null)}
                        >
                          <div className="flex items-center">
                            {(hoveredPage === pagePath || selectedPages.size > 0 || isBulkMode) && (
                              <input
                                type="checkbox"
                                checked={selectedPages.has(pagePath)}
                                onChange={() => togglePageSelection(pagePath)}
                                onClick={e => e.stopPropagation()}
                                className="absolute left-3 z-10 w-3.5 h-3.5 accent-blue-600 cursor-pointer shadow-sm hover:scale-110 transition-transform"
                              />
                            )}
                            <button
                              onClick={() => fetchPageContent(pagePath)}
                              className={`w-full text-left py-2 pl-8 pr-2 rounded-lg text-sm transition-colors flex items-center ${
                                selectedPage === pagePath
                                  ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-bold'
                                  : 'hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300'
                              }`}
                            >
                              <FileText className="w-4 h-4 mr-2 flex-shrink-0 opacity-40" />
                              <span className={`break-all line-clamp-2 leading-tight${
                                pagesMetadata[pagePath]?.read === false && selectedPage !== pagePath
                                  ? ' font-semibold text-gray-900 dark:text-white'
                                  : ''
                              }`}>
                                {pagePath.split('/').pop()?.replace('.md', '').replace(/-/g, ' ')}
                              </span>
                            </button>
                            {hoveredPage === pagePath && renamingPage !== pagePath && (
                              <button
                                onClick={() => {
                                  setRenamingPage(pagePath);
                                  setRenamePageValue(pagePath.split('/').pop()?.replace('.md', '').replace(/-/g, ' ') || '');
                                }}
                                className="ml-2 p-1 rounded hover:bg-blue-100 dark:hover:bg-blue-900/30 text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors mr-2"
                              >
                                <Pencil className="w-4 h-4" />
                              </button>
                            )}
                          </div>
                          {renamingPage === pagePath && (
                            <div className="pl-8 pr-2 py-2 flex gap-2">
                              <input
                                type="text"
                                value={renamePageValue}
                                onChange={(e) => setRenamePageValue(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') handleRenamePage(pagePath);
                                  if (e.key === 'Escape') { setRenamingPage(null); setRenamePageValue(''); }
                                }}
                                autoFocus
                                className="flex-1 px-2 py-1 text-sm border border-blue-400 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                              />
                              <button
                                onClick={() => handleRenamePage(pagePath)}
                                className="px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
                              >
                                Save
                              </button>
                              <button
                                onClick={() => { setRenamingPage(null); setRenamePageValue(''); }}
                                className="px-2 py-1 text-xs bg-gray-300 dark:bg-gray-600 text-gray-900 dark:text-gray-100 rounded hover:bg-gray-400"
                              >
                                Cancel
                              </button>
                            </div>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        )}
          </>
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

      {/* Main Content - Markdown View */}
      <div className={`flex-grow overflow-y-auto bg-white dark:bg-gray-900 flex-col relative ${!isDesktop && (showMobileList || showChat) ? 'hidden' : 'flex'}`}>
        {/* Navigation Header */}
        <div className="hidden lg:flex border-b dark:border-gray-800 px-8 py-4 items-center justify-between sticky top-0 bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm z-10">
          <div className="flex items-center space-x-2">
            <button
              onClick={handleBack}
              disabled={historyStack.length === 0 || isEditing}
              className={`p-1.5 rounded-md transition-colors ${
                historyStack.length === 0 || isEditing ? 'text-gray-300 dark:text-gray-700 cursor-not-allowed' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
              title="Back"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <button
              onClick={handleForward}
              disabled={forwardStack.length === 0 || isEditing}
              className={`p-1.5 rounded-md transition-colors ${
                forwardStack.length === 0 || isEditing ? 'text-gray-300 dark:text-gray-700 cursor-not-allowed' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
              title="Forward"
            >
              <ArrowRight className="w-5 h-5" />
            </button>
            {selectedPage && (
              <span className="ml-4 text-sm font-medium text-gray-500 dark:text-gray-400 truncate max-w-[160px] sm:max-w-xs">
                {selectedPage.split('/').pop()?.replace('.md', '').replace(/-/g, ' ')}
              </span>
            )}
          </div>

          {selectedPage && (
            <div className="flex items-center space-x-2">
              {selectedPages.size === 0 && (
                <>
                  {isEditing ? (
                    <>
                      <button
                        onClick={handleSave}
                        disabled={isSaving}
                        className="flex items-center px-3 py-1.5 bg-green-600 text-white rounded-md text-sm font-medium hover:bg-green-700 transition-colors disabled:opacity-50"
                      >
                        {isSaving ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <Save className="w-4 h-4 mr-1.5" />}
                        Save
                      </button>
                      <button
                        onClick={() => {
                          setIsEditing(false);
                          setEditedContent(content || '');
                        }}
                        disabled={isSaving}
                        className="flex items-center px-3 py-1.5 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-md text-sm font-medium hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                      >
                        <X className="w-4 h-4 mr-1.5" />
                        Cancel
                      </button>
                    </>
                  ) : !isSystemPage ? (
                    <button
                      onClick={() => setIsEditing(true)}
                      className="flex items-center px-3 py-1.5 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-md text-sm font-medium hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                    >
                      <Edit3 className="w-4 h-4 mr-1.5" />
                      Edit
                    </button>
                  ) : null}
                  
                  <button
                    onClick={handleDownload}
                    className="p-1.5 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors"
                    title="Download Page"
                  >
                    <Download className="w-5 h-5" />
                  </button>
                  <button
                    onClick={() => setShowMoveDialog(true)}
                    className="p-1.5 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors"
                    title="Move to folder..."
                  >
                    <ArrowRight className="w-5 h-5" />
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
              {selectedPages.size > 0 && (
                <span className="text-xs font-semibold text-amber-600 bg-amber-50 px-3 py-1.5 rounded-md border border-amber-100">
                  Bulk mode active
                </span>
              )}
            </div>
          )}
        </div>

        <div className="p-8 flex-grow pb-28 lg:pb-8 min-w-0 overflow-x-hidden">
          {contentLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="animate-spin mr-2" /> Loading content...
            </div>
          ) : isEditing ? (
            <div data-color-mode="light" className="w-full h-full min-h-[500px] dark:invert dark:hue-rotate-180">
              <MDEditor
                value={editedContent}
                onChange={(val) => setEditedContent(val || '')}
                height="100%"
                preview="edit"
                className="w-full h-full"
              />
            </div>
          ) : content ? (
            <>
            {selectedPage && !isEditing && !isSystemPage && (
              <div className="flex flex-wrap items-center gap-1.5 px-6 pb-3 pt-1 border-b border-gray-100 dark:border-gray-800 bg-gray-50/30 dark:bg-gray-800/30 -mx-8 mb-4">
                {pageTags.map(tag => (
                  <span key={tag}
                        className="inline-flex items-center gap-1 text-xs px-3 py-1 rounded-full bg-blue-50 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 border border-blue-100 dark:border-blue-800 shadow-sm font-medium">
                    {tag}
                    <button onClick={() => handleRemoveTag(tag)}
                            className="text-blue-500 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-200 ml-1 leading-none">×</button>
                  </span>
                ))}
                {addingTag ? (
                  <div className="relative">
                    <input
                      autoFocus
                      value={newTagInput}
                      onChange={e => setNewTagInput(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') handleAddTag(newTagInput);
                        if (e.key === 'Escape') { setAddingTag(false); setNewTagInput(''); }
                      }}
                      placeholder="tag name"
                      className="text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded px-2 py-0.5 text-gray-900 dark:text-gray-100 outline-none w-28"
                      list="tag-vocab"
                    />
                    <datalist id="tag-vocab">
                      {tagVocabulary
                        .filter(t => !pageTags.includes(t))
                        .map(t => <option key={t} value={t} />)}
                    </datalist>
                  </div>
                ) : (
                  <button onClick={() => setAddingTag(true)}
                          className="text-xs text-gray-500 hover:text-gray-300 px-1">
                    + tag
                  </button>
                )}
                {/* AI suggestion chips */}
                {suggestedTags.map(tag => (
                  <span key={tag} className="inline-flex items-center gap-1 text-xs px-3 py-1 rounded-full bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 border border-green-100 dark:border-green-800 shadow-sm font-medium">
                    ✦ {tag}
                    <button onClick={() => handleAcceptSuggestedTag(tag)}
                            className="text-green-600 dark:text-green-400 hover:text-green-800 dark:hover:text-green-200 font-bold ml-1">Accept</button>
                    <button onClick={() => setSuggestedTags(prev => prev.filter(t => t !== tag))}
                            className="text-green-500 dark:text-green-500 hover:text-green-700 dark:hover:text-green-300 ml-1">×</button>
                  </span>
                ))}
              </div>
            )}
            <div className="wiki-doc prose prose-slate dark:prose-invert max-w-4xl mx-auto break-words">
              {(() => {
                 const { tags, content: cleanContent } = parseFrontmatter(content);
                 return (
                   <>
                     {tags.length > 0 && (
                       <div className="flex flex-wrap gap-2 mb-8 p-4 bg-gray-50/80 dark:bg-gray-800/80 rounded-xl border border-gray-100 dark:border-gray-700 shadow-sm backdrop-blur-sm">
                         {tags.map((t, idx) => (
                           <span key={idx} className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 shadow-sm uppercase tracking-wider">
                             <span className="text-gray-400 dark:text-gray-500 mr-2 text-[10px]">{t.key}:</span>
                             {isEditing
                               ? <span className="text-blue-600 dark:text-blue-400 font-bold">{renderFrontmatterValue(t.value)}</span>
                               : <FrontmatterValue fieldKey={t.key} raw={t.value} />
                             }
                           </span>
                         ))}
                       </div>
                     )}
                     <ReactMarkdown
                       remarkPlugins={[remarkGfm]}
                       components={{
                         // Imported pages carry wide tables — a job's people roster is
                         // five columns and some role titles run to 48 characters — so
                         // they scroll inside their own box rather than overflowing the
                         // prose column. The box carries the border and shadow; see
                         // wiki-doc.css.
                         table: ({ node, ...props }) => (
                           <div className="wiki-table-scroll">
                             <table {...props} />
                           </div>
                         ),
                         // Status tokens are written as inline code by the ingest
                         // (`staff (UK)`, `freelance`) because markdown cannot carry an
                         // attribute. Tag them here so the stylesheet can show staff in
                         // the accent colour and leave freelance grey — freelance is the
                         // default on a callsheet, so staff is the exception worth
                         // noticing.
                         code: ({ node, children, ...props }) => {
                           const text = String(children);
                           const badge = /^staff\b/i.test(text)
                             ? 'staff'
                             : /^freelance$/i.test(text)
                             ? 'freelance'
                             : undefined;
                           return <code {...props} data-badge={badge}>{children}</code>;
                         },
                         a: ({ node, ...props }) => {
                           const isInternal = props.href?.startsWith('#');
                           if (isInternal) {
                             const ref = props.href?.slice(1); // e.g. "clients__louis-vuitton"
                             const pagePath = ref?.replace('__', '/') + '.md'; // "clients/louis-vuitton.md"
                             return (
                               <a
                                 {...props}
                                 onClick={(e) => {
                                   e.preventDefault();
                                   if (pagePath) fetchPageContent(pagePath);
                                 }}
                                 className="text-blue-600 hover:underline cursor-pointer font-medium"
                               >
                                 {props.children}
                               </a>
                             );
                           }
                           return (
                             <a 
                               {...props} 
                               className="text-blue-600 hover:underline" 
                               target="_blank" 
                               rel="noopener noreferrer" 
                             />
                           );
                         }
                       }}
                     >
                       {processWikiLinks(cleanContent, pageTree)}
                     </ReactMarkdown>
                   </>
                 );
              })()}

              {/* Backlinks Section */}
              {backlinks.length > 0 && (
                <div className="mt-12 pt-8 border-t border-gray-100 dark:border-gray-800">
                  <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-4 flex items-center">
                    <FileText className="w-5 h-5 mr-2 opacity-50" />
                    Linked Mentions
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {backlinks.map((link) => (
                      <button
                        key={link}
                        onClick={() => fetchPageContent(link)}
                        className="text-left p-4 rounded-lg border border-gray-100 dark:border-gray-800 hover:border-blue-200 dark:hover:border-blue-800 hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-all group"
                      >
                        <div className="text-sm font-medium text-blue-600 dark:text-blue-400 group-hover:text-blue-700 dark:group-hover:text-blue-300 truncate">
                          {link.split('/').pop()?.replace('.md', '').replace(/-/g, ' ')}
                        </div>
                        <div className="text-xs text-gray-400 dark:text-gray-500 mt-1 uppercase tracking-wider">
                          Page Reference
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-center px-6 overflow-y-auto py-10">
              <img
                src={octopusLight}
                alt="Faragopedia"
                className="w-28 h-28 mb-6 dark:hidden opacity-90"
              />
              <img
                src={octopusDark}
                alt="Faragopedia"
                className="w-28 h-28 mb-6 hidden dark:block opacity-90"
              />

              {totalPageCount === 0 ? (
                <>
                  <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-200 mb-2">
                    Welcome to your wiki
                  </h2>
                  <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md mb-8 leading-relaxed">
                    Faragopedia turns your source documents into a structured, linked knowledge base.
                    Import files or create a page to get started — the AI will help organize what you bring in.
                  </p>
                  <div className="flex flex-wrap items-center justify-center gap-3 mb-10">
                    <button
                      onClick={() => setShowNewPageMenu(true)}
                      className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-500 transition-colors shadow-sm"
                    >
                      <FilePlus className="w-4 h-4" />
                      New Page
                    </button>
                    <button
                      onClick={() => selectedFolder && setShowImportModal(true)}
                      disabled={!selectedFolder}
                      title={selectedFolder ? 'Import markdown files' : 'Select a folder first'}
                      className="flex items-center gap-2 px-4 py-2 bg-gray-50 dark:bg-gray-800 text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      <Upload className="w-4 h-4" />
                      Import Pages
                    </button>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-xl text-left">
                    <div className="flex items-start gap-2.5">
                      <Link2 className="w-4 h-4 text-gray-400 dark:text-gray-500 mt-0.5 shrink-0" />
                      <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
                        Use <code className="text-gray-600 dark:text-gray-300">[[Page Name]]</code> to link pages together.
                      </p>
                    </div>
                    <div className="flex items-start gap-2.5">
                      <Tags className="w-4 h-4 text-gray-400 dark:text-gray-500 mt-0.5 shrink-0" />
                      <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
                        Tag pages to filter and organize as your wiki grows.
                      </p>
                    </div>
                    <div className="flex items-start gap-2.5">
                      <Sparkles className="w-4 h-4 text-gray-400 dark:text-gray-500 mt-0.5 shrink-0" />
                      <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
                        Open the AI chat to ask questions about anything in your wiki.
                      </p>
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-200 mb-2">
                    Welcome to Faragopedia
                  </h2>
                  <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md mb-2 leading-relaxed">
                    Your team's structured, linked knowledge base — every source document ingested here
                    becomes a searchable, cross-referenced wiki page. Select a page from the list to view
                    its content, or ask the AI chat a question about anything below.
                  </p>
                  <p className="text-xs text-gray-400 dark:text-gray-600 mb-8">
                    {totalPageCount} page{totalPageCount !== 1 ? 's' : ''} across{' '}
                    {entityTypeCount} {entityTypeCount !== 1 ? 'sections' : 'section'}
                    {totalUnreadCount > 0 && ` · ${totalUnreadCount} unread`}
                  </p>

                  {sectionStats.length > 0 && (
                    <table className="w-full max-w-md text-sm text-left mb-10 border-collapse">
                      <thead>
                        <tr className="border-b border-gray-100 dark:border-gray-800">
                          <th className="py-2 font-semibold text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wider">Section</th>
                          <th className="py-2 font-semibold text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wider text-right">Pages</th>
                          <th className="py-2 font-semibold text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wider text-right">Unread</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sectionStats.map(stat => (
                          <tr
                            key={stat.section}
                            onClick={() => { toggleSection(stat.section); setSelectedFolder(stat.section); }}
                            className="border-b border-gray-50 dark:border-gray-800/60 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
                          >
                            <td className="py-2 text-gray-700 dark:text-gray-300">{stat.name}</td>
                            <td className="py-2 text-right text-gray-500 dark:text-gray-400">{stat.total}</td>
                            <td className="py-2 text-right">
                              {stat.unread > 0 ? (
                                <span className="px-1.5 py-0.5 rounded-full text-xs font-medium bg-blue-500 text-white leading-none">
                                  {stat.unread}
                                </span>
                              ) : (
                                <span className="text-gray-300 dark:text-gray-600">—</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-xl text-left">
                    <div className="flex items-start gap-2.5">
                      <Link2 className="w-4 h-4 text-gray-400 dark:text-gray-500 mt-0.5 shrink-0" />
                      <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
                        Use <code className="text-gray-600 dark:text-gray-300">[[Page Name]]</code> to link pages together.
                      </p>
                    </div>
                    <div className="flex items-start gap-2.5">
                      <Tags className="w-4 h-4 text-gray-400 dark:text-gray-500 mt-0.5 shrink-0" />
                      <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
                        Tag pages to filter and organize as your wiki grows.
                      </p>
                    </div>
                    <div className="flex items-start gap-2.5">
                      <Sparkles className="w-4 h-4 text-gray-400 dark:text-gray-500 mt-0.5 shrink-0" />
                      <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
                        Open the AI chat to ask questions about anything in your wiki.
                      </p>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
        
        {/* Floating Chat Button for Main Content */}
        {!showChat && selectedPage && (
          <button
            onClick={() => setShowChat(true)}
            className="fixed bottom-6 right-6 p-4 bg-gray-900 text-white rounded-full shadow-xl hover:bg-black hover:scale-105 active:scale-95 transition-all z-40 flex items-center justify-center transform"
            title="Open AI Chat"
          >
            <MessageSquare className="w-6 h-6" />
          </button>
        )}
      </div>

      {/* Chat Drag Handle Gutter */}
      {isDesktop && showChat && (
        <div
          onMouseDown={handleChatMouseDown}
          className="w-1 bg-transparent hover:bg-purple-400 cursor-col-resize transition-colors z-20 flex-shrink-0"
        />
      )}

      {/* Right Sidebar - Chat Panel */}
      {showChat && (
        <div 
          className={`border-l dark:border-gray-800 bg-white dark:bg-gray-900 flex-col flex-shrink-0 relative ${!isDesktop ? 'fixed inset-0 w-full z-50 flex shadow-2xl animate-in slide-in-from-right duration-300' : 'flex'}`}
          style={isDesktop ? { width: chatWidth } : undefined}
        >
          <ChatPanel onLinkClick={(path) => { setShowChat(false); fetchPageContent(path); }} />
          
          {/* Close checkmark for chat */}
          <button 
            className="absolute top-4 right-4 text-gray-500 hover:bg-gray-100 rounded-full p-1.5 transition-colors z-50"
            onClick={() => setShowChat(false)}
            title="Close Chat"
          >
            <X className="w-5 h-5"/>
          </button>
          
          {/* Floating Mobile Toggle Button for Chat -> Page */}
          {!isDesktop && (
            <button
              onClick={() => setShowChat(false)}
              className="absolute top-1/2 left-0 -translate-y-1/2 p-3 bg-gray-900 border border-l-0 border-gray-700 text-white rounded-r-xl shadow-xl hover:bg-black active:scale-95 transition-all z-50 flex items-center justify-center transform"
              title="Back to Page"
            >
              <FileText className="w-5 h-5" />
            </button>
          )}
        </div>
      )}

      {/* Floating Mobile Toggle Button */}
      {!isDesktop && !showMobileList && !showChat && (
        <button
          onClick={() => setShowMobileList(true)}
          className="fixed bottom-6 left-6 p-4 bg-gray-900 text-white rounded-full shadow-xl hover:bg-black hover:scale-105 active:scale-95 transition-all z-40 flex items-center justify-center transform"
          title="Back to Pages List"
        >
          <ArrowLeft className="w-6 h-6" />
        </button>
      )}

      {/* Floating Mobile Bulk Mode Button */}
      {!isDesktop && showMobileList && selectedPages.size === 0 && !isBulkMode && (
        <button
          onClick={() => setIsBulkMode(true)}
          className="fixed bottom-6 right-6 p-4 bg-gray-900 text-white rounded-full shadow-xl hover:bg-black hover:scale-105 active:scale-95 transition-all z-40 flex items-center justify-center transform"
          title="Enter Bulk Mode"
        >
          <ListChecks className="w-6 h-6" />
        </button>
      )}

      {/* Floating Mobile Action Menu */}
      {!isDesktop && !showMobileList && !showChat && selectedPage && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex flex-col items-center">
          {showActionMenu && (
            <div className="flex flex-col items-stretch space-y-3 mb-4 animate-in slide-in-from-bottom-2 fade-in duration-200">
              {selectedPages.size === 0 && (
                <>
                  {showMobileRenameInput ? (
                    <div className="bg-white dark:bg-gray-800 rounded-full shadow-md px-5 py-3 flex gap-2">
                      <input
                        type="text"
                        value={renamePageValue}
                        onChange={(e) => setRenamePageValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && selectedPage) handleRenamePage(selectedPage);
                          if (e.key === 'Escape') { setShowMobileRenameInput(false); setRenamePageValue(''); }
                        }}
                        autoFocus
                        className="flex-1 px-2 py-1 text-sm border border-blue-400 rounded bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                      />
                      <button
                        onClick={() => selectedPage && handleRenamePage(selectedPage)}
                        className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
                      >
                        Save
                      </button>
                      <button
                        onClick={() => { setShowMobileRenameInput(false); setRenamePageValue(''); }}
                        className="px-3 py-1 text-xs bg-gray-300 dark:bg-gray-600 text-gray-900 dark:text-gray-100 rounded hover:bg-gray-400"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <>
                      {isEditing ? (
                        <>
                          <button
                            onClick={() => { handleSave(); setShowActionMenu(false); }}
                            disabled={isSaving}
                            className="flex justify-start items-center px-5 py-2 bg-green-600 text-white rounded-full shadow-md text-sm font-medium hover:bg-green-700 transition-colors disabled:opacity-50"
                          >
                            {isSaving ? <Loader2 className="w-4 h-4 animate-spin mr-3" /> : <Save className="w-4 h-4 mr-3" />}
                            Save
                          </button>
                          <button
                            onClick={() => {
                              setIsEditing(false);
                              setEditedContent(content || '');
                              setShowActionMenu(false);
                            }}
                            disabled={isSaving}
                            className="flex justify-start items-center px-5 py-2 bg-gray-100 text-gray-700 rounded-full shadow-md text-sm font-medium hover:bg-gray-200 transition-colors"
                          >
                            <X className="w-4 h-4 mr-3" />
                            Cancel
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => { setIsEditing(true); setShowActionMenu(false); }}
                          className="flex justify-start items-center px-5 py-2 bg-white text-gray-700 rounded-full shadow-md text-sm font-medium hover:bg-gray-50 transition-colors"
                        >
                          <Edit3 className="w-4 h-4 mr-3" />
                          Edit
                        </button>
                      )}

                      <button
                        onClick={() => {
                          if (selectedPage) setRenamePageValue(selectedPage.split('/').pop()?.replace('.md', '').replace(/-/g, ' ') || '');
                          setShowMobileRenameInput(true);
                        }}
                        className="flex justify-start items-center px-5 py-2 bg-white text-gray-700 rounded-full shadow-md text-sm font-medium hover:bg-gray-50 transition-colors"
                      >
                        <Pencil className="w-4 h-4 mr-3" />
                        Rename
                      </button>

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
                </>
              )}
              {selectedPages.size > 0 && (
                <div className="bg-gray-900/90 backdrop-blur-md p-4 rounded-3xl shadow-2xl border border-white/10 space-y-3">
                  <div className="text-xs font-bold text-gray-400 uppercase tracking-widest text-center mb-1">{selectedPages.size} Selected</div>
                  <button
                    onClick={() => { setShowBulkMoveDialog(true); setShowActionMenu(false); }}
                    className="w-full flex justify-center items-center py-3 bg-blue-600 text-white rounded-2xl font-bold"
                  >
                    Bulk Move
                  </button>
                  <button
                    onClick={() => { handleBulkDownloadPages(); setShowActionMenu(false); }}
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

      {/* New Folder Dialog */}
      {showNewFolderDialog && (
        <div className="fixed inset-0 bg-black/30 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setShowNewFolderDialog(false)}>
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-xl p-6 w-full max-w-sm space-y-4 border border-gray-100 dark:border-gray-800" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">New Folder</h3>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Display Name</label>
              <input
                autoFocus
                value={newFolderDisplayName}
                onChange={e => {
                  setNewFolderDisplayName(e.target.value);
                  setNewFolderName(e.target.value.toLowerCase().replace(/\s+/g, '-'));
                }}
                className="w-full border dark:border-gray-700 bg-white dark:bg-gray-800 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
                placeholder="e.g. Stylists"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Folder ID</label>
              <input
                value={newFolderName}
                onChange={e => setNewFolderName(e.target.value)}
                className="w-full border dark:border-gray-700 bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2 text-sm text-gray-500 dark:text-gray-400"
                placeholder="e.g. stylists"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description (for AI context)</label>
              <input
                value={newFolderDescription}
                onChange={e => setNewFolderDescription(e.target.value)}
                className="w-full border dark:border-gray-700 bg-white dark:bg-gray-800 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
                placeholder="e.g. Hair and makeup stylists we work with"
              />
            </div>
            <div className="flex justify-end space-x-2">
              <button onClick={() => setShowNewFolderDialog(false)} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg">Cancel</button>
              <button
                onClick={handleCreateFolder}
                disabled={!newFolderName.trim() || !newFolderDisplayName.trim()}
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Move Page Dialog */}
      {showMoveDialog && selectedPage && (
        <div className="fixed inset-0 bg-black/30 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setShowMoveDialog(false)}>
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-xl p-6 w-full max-w-xs space-y-3 border border-gray-100 dark:border-gray-800" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Move to...</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">Move "{selectedPage.split('/').pop()?.replace('.md', '').replace(/-/g, ' ')}" to:</p>
            <div className="space-y-1">
              {Object.entries(entityTypes)
                .filter(([key]) => key !== selectedPage.split('/')[0])
                .map(([key, data]) => (
                  <button
                    key={key}
                    onClick={() => handleMovePage(key)}
                    className="w-full text-left px-4 py-2 text-sm rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/50 hover:text-blue-700 dark:hover:text-blue-300 text-gray-700 dark:text-gray-300 transition-colors"
                  >
                    {data.name || key}
                  </button>
                ))}
            </div>
            <button onClick={() => setShowMoveDialog(false)} className="w-full text-center text-sm text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 mt-2">Cancel</button>
          </div>
        </div>
      )}

      {error && (
        <ErrorToast message={error} onDismiss={() => setError(null)} />
      )}

      {showBulkMoveDialog && (
        <MoveDialog
          selectedCount={selectedPages.size}
          initialDestination={
            selectedPages.size > 0
              ? (Array.from(selectedPages)[0].split('/')[0] as any)
              : undefined
          }
          onConfirm={handleBulkMove}
          onClose={() => setShowBulkMoveDialog(false)}
        />
      )}

      {showConfirm && (
        <ConfirmDialog
          message={`Archive ${selectedPages.size} page${selectedPages.size === 1 ? '' : 's'}? This can be undone from the Archive view.`}
          confirmLabel="Archive"
          onConfirm={handleBulkArchivePages}
          onCancel={() => setShowConfirm(false)}
        />
      )}

      {showImportModal && selectedFolder && (
        <ImportWikiModal
          folder={selectedFolder}
          onClose={() => setShowImportModal(false)}
          onImported={fetchPages}
        />
      )}
      </div>
    </div>
  );
};

export default WikiView;

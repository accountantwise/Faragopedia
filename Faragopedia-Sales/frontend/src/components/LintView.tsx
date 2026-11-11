import React, { useState, useRef } from 'react';
import { Activity, Loader2, AlertCircle, AlertTriangle, Lightbulb, CheckSquare, Square, Wrench, CheckCircle2 } from 'lucide-react';
import { API_BASE } from '../config';
import SnapshotsPanel from './SnapshotsPanel';

interface LintFinding {
  severity: 'error' | 'warning' | 'suggestion';
  page: string;
  description: string;
  fix_confidence: 'full' | 'stub' | 'needs_source';
  fix_description: string;
}

interface LintReport {
  findings: LintFinding[];
  summary: string;
}

interface FixReport {
  files_changed: string[];
  skipped: string[];
  summary: string;
  snapshot_id: string;
}

const SEVERITY_CONFIG = {
  error: {
    label: 'Errors',
    icon: <AlertCircle className="w-4 h-4 text-red-500" />,
    cardClass: 'bg-red-50 dark:bg-red-900/10 border-red-200 dark:border-red-900/30',
    badgeClass: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400',
  },
  warning: {
    label: 'Warnings',
    icon: <AlertTriangle className="w-4 h-4 text-amber-500" />,
    cardClass: 'bg-amber-50 dark:bg-amber-900/10 border-amber-200 dark:border-amber-900/30',
    badgeClass: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400',
  },
  suggestion: {
    label: 'Suggestions',
    icon: <Lightbulb className="w-4 h-4 text-blue-500" />,
    cardClass: 'bg-blue-50 dark:bg-blue-900/10 border-blue-200 dark:border-blue-900/30',
    badgeClass: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400',
  },
};

const FIX_CONFIDENCE_CONFIG = {
  full: { label: 'Full fix', className: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400' },
  stub: { label: 'Stub', className: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400' },
  needs_source: { label: 'Needs source', className: 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400' },
};

const LintView: React.FC = () => {
  const [report, setReport] = useState<LintReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [applying, setApplying] = useState(false);
  const [fixReport, setFixReport] = useState<FixReport | null>(null);
  const [snapshotsKey, setSnapshotsKey] = useState(0);
  const snapshotsPanelRef = useRef<HTMLDivElement>(null);

  const runLint = async () => {
    setLoading(true);
    setError(null);
    setReport(null);
    setSelected(new Set());
    setFixReport(null);
    try {
      const response = await fetch(`${API_BASE}/lint`, { method: 'POST' });
      if (!response.ok) throw new Error('Lint request failed');
      const data: LintReport = await response.json();
      setReport(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const toggleSelected = (index: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(index) ? next.delete(index) : next.add(index);
      return next;
    });
  };

  const selectAll = () => {
    if (!report) return;
    setSelected(new Set(report.findings.map((_, i) => i)));
  };

  const deselectAll = () => setSelected(new Set());

  const applySelected = async () => {
    if (!report || selected.size === 0) return;
    setApplying(true);
    setFixReport(null);
    try {
      const selectedFindings = Array.from(selected).map(i => report.findings[i]);
      const response = await fetch(`${API_BASE}/lint/fix`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ findings: selectedFindings }),
      });
      if (!response.ok) throw new Error('Fix request failed');
      const data: FixReport = await response.json();
      setFixReport(data);
      setSelected(new Set());
      setSnapshotsKey(k => k + 1);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setApplying(false);
    }
  };

  const allSelected = report ? selected.size === report.findings.length : false;

  return (
    <div className="h-full w-full overflow-y-auto">
      <div className="p-8 md:p-12 max-w-4xl mx-auto pb-24">
        <h1 className="text-4xl font-extrabold text-gray-900 dark:text-gray-100 mb-6 tracking-tight">Wiki Lint</h1>
        <p className="text-xl text-gray-500 dark:text-gray-400 mb-8 leading-relaxed">
          Deep AI analysis — orphan pages, contradictions, missing entities, and data gaps.
        </p>

        <button
          onClick={runLint}
          disabled={loading}
          className="flex items-center px-6 py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 transition-colors disabled:opacity-50 mb-8 shadow-sm"
        >
          {loading
            ? <Loader2 className="w-5 h-5 animate-spin mr-2" />
            : <Activity className="w-5 h-5 mr-2" />
          }
          Lint
        </button>

        {loading && (
          <div className="mt-4 space-y-1">
            <div className="flex items-center gap-2 text-sm text-blue-500 dark:text-blue-400">
              <Loader2 className="w-4 h-4 animate-spin flex-shrink-0" />
              <span>This takes 20–40 seconds — reading all pages and running AI analysis</span>
            </div>
            <div className="space-y-3 max-w-xl animate-pulse mt-4">
              <div className="h-4 bg-gray-200 dark:bg-gray-800 rounded-full w-3/4"></div>
              <div className="h-4 bg-gray-200 dark:bg-gray-800 rounded-full w-full"></div>
              <div className="h-4 bg-gray-200 dark:bg-gray-800 rounded-full w-5/6"></div>
            </div>
          </div>
        )}

        {error && (
          <div className="p-4 bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-900/30 rounded-xl text-red-700 dark:text-red-400 text-sm mb-4">
            {error}
          </div>
        )}

        {fixReport && (
          <div className="p-4 bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-900/30 rounded-xl mb-6">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0" />
              <p className="text-green-800 dark:text-green-300 font-semibold">{fixReport.summary}</p>
            </div>
            {fixReport.files_changed.length > 0 && (
              <ul className="text-sm text-green-700 dark:text-green-400 space-y-1 ml-7">
                {fixReport.files_changed.map(f => (
                  <li key={f} className="font-mono">{f}</li>
                ))}
              </ul>
            )}
            {fixReport.skipped.length > 0 && (
              <div className="mt-3 ml-7">
                <p className="text-sm font-medium text-amber-700 dark:text-amber-400">Skipped:</p>
                <ul className="text-sm text-amber-600 dark:text-amber-500 space-y-1 mt-1">
                  {fixReport.skipped.map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </div>
            )}
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-3 ml-7">
              Snapshot saved ·{' '}
              <button
                onClick={() => snapshotsPanelRef.current?.scrollIntoView({ behavior: 'smooth' })}
                className="text-blue-600 dark:text-blue-400 hover:underline"
              >
                restore if needed
              </button>
            </p>
          </div>
        )}

        {report && (
          <div className="space-y-6">
            <div className="flex items-center gap-3 p-4 bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-900/30 rounded-xl">
              <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400 flex-shrink-0" />
              <p className="text-green-800 dark:text-green-300 font-semibold">{report.summary}</p>
            </div>
            <div className="flex items-center justify-between">
              {report.findings.length > 0 && (
                <button
                  onClick={allSelected ? deselectAll : selectAll}
                  className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
                >
                  {allSelected ? 'Deselect all' : 'Select all'}
                </button>
              )}
            </div>

            {(['error', 'warning', 'suggestion'] as const).map(severity => {
              const findings = report.findings
                .map((f, i) => ({ finding: f, index: i }))
                .filter(({ finding }) => finding.severity === severity);
              if (findings.length === 0) return null;
              const config = SEVERITY_CONFIG[severity];
              return (
                <div key={severity}>
                  <h3 className="flex items-center space-x-2 text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider mb-3">
                    {config.icon}
                    <span>{config.label} ({findings.length})</span>
                  </h3>
                  <ul className="space-y-2">
                    {findings.map(({ finding, index }) => {
                      const isChecked = selected.has(index);
                      const confidenceConfig = FIX_CONFIDENCE_CONFIG[finding.fix_confidence];
                      return (
                        <li
                          key={index}
                          className={`p-4 rounded-xl border ${config.cardClass} cursor-pointer`}
                          onClick={() => toggleSelected(index)}
                        >
                          <div className="flex items-start gap-3">
                            <div className="mt-0.5 flex-shrink-0">
                              {isChecked
                                ? <CheckSquare className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                                : <Square className="w-5 h-5 text-gray-400 dark:text-gray-600" />
                              }
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex flex-wrap items-center gap-2 mb-1">
                                <span className={`inline-block text-xs font-mono px-2 py-0.5 rounded-md ${config.badgeClass}`}>
                                  {finding.page}
                                </span>
                                <span className={`inline-block text-xs px-2 py-0.5 rounded-md font-medium ${confidenceConfig.className}`}>
                                  {confidenceConfig.label}
                                </span>
                              </div>
                              <p className="text-sm text-gray-700 dark:text-gray-300">{finding.description}</p>
                              {finding.fix_description && (
                                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 italic">{finding.fix_description}</p>
                              )}
                            </div>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}

            {report.findings.length === 0 && (
              <p className="text-green-600 dark:text-green-400 font-medium">Wiki is clean — no issues found.</p>
            )}

            {selected.size > 0 && (
              <div className="sticky bottom-4 flex flex-col gap-2">
                <button
                  onClick={applySelected}
                  disabled={applying}
                  className="flex items-center px-6 py-3 bg-green-600 text-white rounded-xl font-semibold hover:bg-green-700 transition-colors disabled:opacity-50 shadow-lg"
                >
                  {applying
                    ? <Loader2 className="w-5 h-5 animate-spin mr-2" />
                    : <Wrench className="w-5 h-5 mr-2" />
                  }
                  {applying ? 'Applying fixes…' : `Apply ${selected.size} selected`}
                </button>
                {applying && (
                  <div className="flex items-center gap-2 text-sm text-blue-500 dark:text-blue-400 px-1">
                    <Loader2 className="w-4 h-4 animate-spin flex-shrink-0" />
                    <span>Writing changes to wiki — a snapshot is being created first</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        <div ref={snapshotsPanelRef}>
          <SnapshotsPanel key={snapshotsKey} />
        </div>
      </div>
    </div>
  );
};

export default LintView;

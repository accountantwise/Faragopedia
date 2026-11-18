/**
 * The company enrichment writes "_Sources: … (as of 2026-10-26)._" at the end of
 * a page's overview. Simon asked for that date to be visible (feedback #5,
 * Oct 2026), so the page header shows it as "Information correct as of …".
 * Returns the latest such date on the page, formatted for display, or null.
 */
export function asOfDate(markdown: string): string | null {
  const dates = Array.from(markdown.matchAll(/\(as of (\d{4}-\d{2}-\d{2})\)/g), m => m[1]).sort();
  const latest = dates[dates.length - 1];
  if (!latest) return null;
  const d = new Date(`${latest}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
}

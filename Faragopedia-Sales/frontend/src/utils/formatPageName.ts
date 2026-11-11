/** Convert a wiki page path like "clients/alexander_mcqueen.md" into a readable label. */
export function formatPageName(path: string): string {
  return path
    .replace(/\.md$/, '')
    .split('/')
    .pop()!
    .replace(/_/g, ' ');
}

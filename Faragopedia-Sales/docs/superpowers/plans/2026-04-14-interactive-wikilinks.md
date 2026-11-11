# Interactive WikiLinks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `[[WikiLinks]]` clickable in the frontend and update project documentation to reflect current progress.

**Architecture:** 
1. Update `AGENTS.md` and `docs/status.md` to reflect the current state and the plan.
2. Modify `WikiView.tsx` to pre-process Markdown content, converting `[[Page Name]]` to internal links, and provide a custom `a` component to handle navigation.
3. Update `CLAUDE.md` and `GEMINI.md` to ensure alignment with `AGENTS.md`.

**Tech Stack:** React, Tailwind CSS, react-markdown.

---

### Task 1: Documentation Update

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/status.md`

- [ ] **Step 1: Update AGENTS.md**
Update the "Current Status" and "Immediate Priorities" sections.

```markdown
## Current Status
**Phase:** 🟡 MVP Development / Prototype Functional
**Last updated:** 2026-04-14

### Immediate Priorities
1. ~~Implement functional LLM Wiki Prototype with Multi-Provider Support~~ ✅
2. ~~Resolve port conflicts and set up local development workflow~~ ✅
3. Implement interactive [[WikiLinks]] in the frontend 👈
4. Implement Backlinks/Linked Mentions
5. Refine AI maintenance logic (automated linting and cross-page synthesis)
```

- [ ] **Step 2: Update docs/status.md**
Add the latest progress (port fix, local setup) to the status log.

- [ ] **Step 3: Commit**
```bash
git add AGENTS.md docs/status.md
git commit -m "docs: update status and agents context with local setup progress"
```

---

### Task 2: Interactive WikiLinks in Frontend

**Files:**
- Modify: `frontend/src/components/WikiView.tsx`

- [ ] **Step 1: Implement content pre-processing and custom renderer**
Modify `WikiView.tsx` to handle the `[[Page Name]]` syntax.

```tsx
// Inside WikiView.tsx

// 1. Add a helper to transform [[WikiLinks]] to [WikiLinks](#WikiLinks)
const processWikiLinks = (text: string) => {
  return text.replace(/\[\[(.*?)\]\]/g, (match, p1) => {
    // Sanitize the link to match filename expectations if necessary
    // But for the label, we keep the original text
    return `[${p1}](#${p1})`;
  });
};

// 2. Update the ReactMarkdown component
<ReactMarkdown
  components={{
    a: ({ node, ...props }) => {
      const isInternal = props.href?.startsWith('#');
      if (isInternal) {
        const pageName = props.href?.slice(1);
        return (
          <a
            {...props}
            onClick={(e) => {
              e.preventDefault();
              if (pageName) fetchPageContent(pageName + '.md');
            }}
            className="text-blue-600 hover:underline cursor-pointer font-medium"
          >
            {props.children}
          </a>
        );
      }
      return <a {...props} className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer" />;
    }
  }}
>
  {processWikiLinks(content || '')}
</ReactMarkdown>
```

- [ ] **Step 2: Verify the change**
Select a page with WikiLinks (e.g., `Summary_test_upload.txt.md` or `Faragopedia.md`) and click a link to verify it loads the target page.

- [ ] **Step 3: Commit**
```bash
git add frontend/src/components/WikiView.tsx
git commit -m "feat(ui): make [[WikiLinks]] interactive in WikiView"
```

---

### Task 3: Align Agent Context Files

**Files:**
- Modify: `CLAUDE.md`
- Modify: `GEMINI.md`

- [ ] **Step 1: Update CLAUDE.md and GEMINI.md**
Ensure both files point to `AGENTS.md` and contain no stale context.

- [ ] **Step 2: Commit**
```bash
git add CLAUDE.md GEMINI.md
git commit -m "docs: align CLAUDE.md and GEMINI.md with latest AGENTS.md"
```

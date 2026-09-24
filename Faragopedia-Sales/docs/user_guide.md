# Faragopedia User Guide and Best Practices

Welcome to Faragopedia! This app is your AI-powered companion for organizing, exploring, and maintaining your knowledge base. Think of the app as having two distinct sides: your **Immutable Sources** (the raw files you upload) and your **Wiki** (the living, interlinked knowledge base the AI builds for you). 

Here is how to get the most out of the system based on best practices.

---

## 1. The Core Workflow

### Step 1: Ingestion (Adding Knowledge)
* **What to do:** Drop your raw files (e.g., meeting notes, client PDF reports, event transcripts) into the system using the **Sources View**.
* **How it works:** Once uploaded, tell the AI to "ingest" the source. The AI reads the document, extracts the key facts, and creates or updates relevant pages in the Wiki. 
* **Best Practice:** Ingest sources one at a time when precision matters. Read the AI's generated files and edit them for accuracy and specific use cases. 

### Step 2: Querying (Extracting Value)
* **What to do:** Use the search bar or standard chat interface to ask questions about your network, clients, or past projects.
* **How it works:** The AI consults the index and wiki pages to synthesize a clear answer with direct citations.
* **Best Practice:** If the AI generates an excellent comparison, table, or analysis during a chat, **copy the response and file it either as a new section in a relevant Wiki page or as a new Wiki page altogether.** Your explorations should compound!

### Step 3: Linting (Maintaining Health)
* **What to do:** Navigate to the **Lint View** to run a system health check.
* **How it works:** The AI actively scans the entire wiki for contradictions, orphan pages (disconnected subjects), and data gaps. It provides actionable "fixes" with confidence ratings.
* **Best Practice:** Run a lint check weekly. Use the "Apply Selected" feature to bulk-fix issues. If the AI makes a mistake, use the **Snapshots Panel** to easily roll back the changes to a previous state.

---

## 2. Navigating the Interface

* **Wiki View:** Your main hub. Browse through dynamically organized folders. Use the **search bar** and **tag chips** to quickly filter down to specific entities (e.g., find all entries tagged `#prospect` or `#apparel`).
* **Sources View:** Review the raw files you’ve uploaded. You can browse, read, and manage (archive/download) these files here. You can also manually trigger ingestion for any pending files.
* **Link View:** The whole wiki's crosslink structure in one map. Pages appear as pills grouped by entity type. **Hover** any page to light it up and draw curves to every page it links to (and every page that links back). **Click** a page to focus it and read its full contents in a side panel — wikilinks inside the panel are clickable, so you can browse page-to-page without leaving the map. The **search bar** filters the map to pages whose content matches. Press **Esc** or click the background to reset.
* **Lint View:** The actionable checklist for your wiki's health. Review the AI's suggestions and apply fixes.

---

## 3. Top Best Practices for Success

**1. Treat your Sources as Sacred:** 
Never try to edit your raw source documents directly to fix a wiki error. Sources are immutable. If something is wrong in the Wiki, update that Wiki page directly and consider curating your sources more closely before ingesting them.

**2. Leverage Bulk Actions for Organization:**
If a strategy shifts or you need to reorganize, use the **Bulk Move** feature to quickly reorganize folders or entities. The system will automatically rewrite all the internal links (`[[WikiLinks]]`) so nothing breaks.

**3. Lean on Tags:**
The AI will suggest tags, but you can manage them directly across the Wiki View. Use tags consistently to make cross-referencing easier (for example, applying `#q3-focus` to specific brands).

**4. The AI is Your Co-Pilot, Not an Autopilot:**
The AI handles the tedious bookkeeping—updating lists, maintaining links, reading old files to check for contradictions. **Your job is to steer.** Ask good questions, provide rich source material, and curate the focus of the app based on your goals.

**5. Backups Are Built-In:**
Don't be afraid to let the AI rewrite chunks of the wiki or apply bulk lint fixes. The system takes snapshots of the database. If a change isn’t what you wanted, you can restore it from the Snapshots Panel with one click.

---
name: literature
description: Systematic literature search and retrieval protocol for peptide chemistry mechanisms using native web tools, PDF parsing, caching, and strict citation auditing.
---

# literature Skill

## 1. Objective

Execute a disciplined, mechanism-grounded literature search for non-standard peptide chemistry, cross-reactivity hazards, protecting group orthogonalities, or catalytic conditions not fully resolved by `extracted_families.json`. Persist verified full-text markdown into `/cache/` and audit citations prior to emission.

## 2. Native Tools & Operational Budgets

Use native model web search. Do not wrap search in a local tool.

- **OpenAI** (`{"type": "web_search"}` on the Responses API):
  - Domain filter is already on the tool. Prefer PMC.
  - At most **one** search unless the first returns nothing citeable.
- **Anthropic** (`web_search_20250305`):
  - `max_uses`: **3** per invocation.
  - Restricted domains: `ncbi.nlm.nih.gov` (PMC), `pubs.acs.org`, `onlinelibrary.wiley.com`, `pubs.rsc.org`, `nature.com`.
- **Rule**: Always append `filetype:pdf` to target primary literature articles directly.
- **Anthropic `web_fetch` (`web_fetch_20250910`)**: `max_uses` **2**, `citations.enabled`.
- **OpenAI**: no native `web_fetch`. Persist search citations with `fetch_and_parse` when the page text is already in context.
- **`fetch_and_parse(url, content, citations)`**:
  - Converts native `web_fetch` HTML/PDF content to markdown under `/cache/`.
  - Returns `{path: "/cache/...", preview: "...", thin_content: bool, error: ...}`.

## 3. Query Construction: Search the Mechanism, Not the Family Name

Search the underlying physical organic chemistry, reagent interactions, or catalytic mechanisms rather than broad family names.

- *Ineffective*: `hydrocarbon stapling disulfide compatibility`
- *Effective*: `ruthenium catalyst thiol poisoning metathesis peptide filetype:pdf`
- *Ineffective*: `cyclization side reactions`
- *Effective*: `HATU guanidinylation slow coupling peptide filetype:pdf`
- *Ineffective*: `disulfide oxidation side reactions`
- *Effective*: `iodine tyrosine tryptophan modification disulfide oxidation filetype:pdf`
- *Ineffective*: `lipidation orthogonal deprotection`
- *Effective*: `Mtt 1% TFA deprotection Trt cleavage selectivity filetype:pdf`

## 4. Disciplined 3-Query Budget Strategy

Do not thrash search tools. Follow this exact escalation ladder:

1. **Query 1 (Narrow)**: Specific chemical mechanism + exact reagent names + `filetype:pdf`.
2. **Query 2 (Broadened Review)**: If Query 1 yields no accessible full-text, remove one specific condition and append `"review"`.
3. **Query 3 (Directed Pairwise Cross-Check)**: Direct two-reagent cross-reactivity search (e.g. `"Alloc Pd(PPh3)4 reduction disulfide"`).
4. **Stopping Rule**: If Queries 1 and 2 produce no citable evidence, STOP. Mark the finding as `inference` without literature. Do not waste the 3rd query repeating the same concept.

## 5. Paywall & Thin-Content Handling

- `allowed_domains` filters search, but paywall abstract gates still occur.
- If `fetch_and_parse` returns `thin_content: true` (cleaned markdown < 500 characters), treat the page as a stub.
- **Hard Rule**: Never cite a `thin_content` stub as verified literature evidence. Move the unsupported claim to `unknowns`.
- Prioritize `ncbi.nlm.nih.gov` (PubMed Central) as it offers the highest probability of unpaywalled full-text access.

## 6. Local Cache Reuse & Citation Audit

- Reuse already fetched papers in `/cache/` using `ls`, `glob`, `grep`, and `read_file` (with offset/limit).
- Shell `execute` may only run `rg`/`ls`/`grep` inside the research root.
- **Audit Requirement**: An external citation (`kind: "external"`) is only valid if `audit_ref(kind="external", ref_or_source=..., basis=...)` locates the file in `/cache/` and matches the basis terms.
- Record key experimental parameters and durable observations in `/memory/AGENTS.md` and `/memory/<request_id>/notes.md`.

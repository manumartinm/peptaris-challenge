# 11 — Literature research sandbox

**Purpose:** The only two tools that touch the network, plus a
local on-disk cache so repeated work within one environment does not
unnecessarily hit the network.

**Read this when:** you need what those tools return, or why an
`external` citation was dropped.

**Prerequisites:** [The Agent](08-agent.md) tool list.
[Axioms](01-axioms.md) 5.

[Index](../plan.md)

---

## Network vs local

`search_literature` and `fetch_and_parse` are the only two tools that
touch the network, capped at **3** and **2** per invocation.
Everything else — `ls`, `read_file` with an offset and limit, `glob`,
`grep` in its several output modes — is local disk, scoped per
invocation.

`fetch_and_parse` downloads, converts PDF or HTML to clean markdown,
and persists the file itself. It returns only a path and a short
preview, never the full content. A second call with the same URL does
not hit the network.

This fetch → markdown path is not a chemistry loop.

Internet is allowed. An uncited outside assertion dressed as corpus
fact is not.

---

## Cache policy

In a source checkout, the sandbox defaults to `research/`; an installed
wheel uses the XDG cache directory. `ROUTE_AGENT_RESEARCH_ROOT` can override
either location. Runtime cache, memory, workspace, and copied skill files are
local artifacts and `research/*` is intentionally gitignored.

If `fetch_and_parse` hit the live web on every rerun, page content could
drift between runs. A warm local cache prevents that within one environment.
A clean clone does not inherit external literature cache content, so
reproducible evaluation must rely on the packaged corpus or explicitly
provisioned, reviewed research artifacts rather than assuming `research/`
was committed.

This also upgrades axiom 5 for literature specifically: `audit_ref`
can re-read the cached file for the terms a citation's `basis`
claims — the same rigor corpus row lookup already had — closing half
of what used to be an unrecoverable gap for `external` provenance.

An `external` citation resolves only if its `source` is available in the
current sandbox cache and its `basis` terms appear in that file.

prev: [Family profiles](10-extracted-families.md) · [Index](../plan.md) · next: [Operational rules](12-operational-rules.md)

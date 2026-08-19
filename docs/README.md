# Documentation

Start with the guide that matches your task:

| Guide | Use it for |
| --- | --- |
| [Getting started](getting-started.md) | Installation, credentials, CLI/API/UI usage, configuration, and troubleshooting |
| [Architecture](architecture.md) | Runtime flow, package boundaries, persistence, failure semantics, and design decisions |
| [Trace Explorer](trace-explorer.md) | React UI, local jobs API, trace views, and frontend development |
| [Domain process notes](plan.md) | Detailed chemistry-process rules from validation through verdict assembly |
| [Releasing](releasing.md) | CI gates, Release Please, wheel verification, and PyPI publication |

Related repository documentation:

- [`../README.md`](../README.md) — product overview and quick start;
- [`../AGENTS.md`](../AGENTS.md) — contributor package map and invariants;
- [`../infra/README.md`](../infra/README.md) — optional local observability stack;
- [`../trace-viewer/README.md`](../trace-viewer/README.md) — concise frontend commands;
- [`../challenge.md`](../challenge.md) — original challenge specification and historical deliverables.

The implemented code and tests are authoritative. Files under `plan/` explain
domain intent and may preserve historical context where explicitly marked.

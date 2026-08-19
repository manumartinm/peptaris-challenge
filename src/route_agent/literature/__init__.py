"""Literature persist and citation audit.

Search and fetch are native provider tools. This package confines
`research_root` paths, persists fetched markdown under `/cache/`, and
audits citations against that cache. OpenAI uses Responses API
`web_search`; Anthropic uses `web_search_20250305` / `web_fetch_20250910`.
"""

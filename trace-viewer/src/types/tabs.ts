export const TABS = [
  { id: "home", label: "Home", group: "overview" },
  { id: "validate", label: "Validate", group: "steps" },
  { id: "walk", label: "Walk", group: "steps" },
  { id: "molecular", label: "Molecular", group: "steps" },
  { id: "intent", label: "Intent", group: "steps" },
  { id: "judge", label: "Judge", group: "steps" },
  { id: "llm", label: "LLM", group: "inspect" },
  { id: "json", label: "JSON", group: "inspect" },
] as const;

export type TabId = (typeof TABS)[number]["id"];

export function isTabId(value: string | null): value is TabId {
  return TABS.some((tab) => tab.id === value);
}

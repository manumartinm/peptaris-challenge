import { TABS, type TabId } from "../types/tabs";

interface TabBarProps {
  active: TabId;
  onChange: (tab: TabId) => void;
}

export function TabBar({ active, onChange }: TabBarProps) {
  return (
    <nav className="tab-bar" aria-label="Trace views">
      {TABS.map((tab, index) => {
        const previous = TABS[index - 1];
        const divider = previous && previous.group !== tab.group;
        return (
          <span key={tab.id} className={divider ? "tab-cluster" : undefined}>
            {divider ? <span className="tab-divider" aria-hidden="true" /> : null}
            <button
              type="button"
              className={tab.id === active ? "tab active" : "tab"}
              onClick={() => onChange(tab.id)}
            >
              {tab.label}
            </button>
          </span>
        );
      })}
    </nav>
  );
}

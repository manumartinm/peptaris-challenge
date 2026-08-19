import type { ReactNode } from "react";
import { humanize } from "../lib/format";

export function EmptyValue() {
  return <span className="empty-value">No disponible</span>;
}

export function StatusChip({ status }: { status: string }) {
  const tone =
    status === "pass" ? "pass" : status === "fail" ? "fail" : status === "degraded" ? "warn" : "neutral";
  return <span className={`chip chip-${tone}`}>{humanize(status)}</span>;
}

export function VerdictChip({ verdict }: { verdict: string }) {
  const tone =
    verdict === "feasible"
      ? "pass"
      : verdict === "feasible_with_changes"
        ? "warn"
        : verdict === "infeasible"
          ? "fail"
          : "neutral";
  return <span className={`chip chip-${tone}`}>{humanize(verdict)}</span>;
}

export function Section({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="panel">
      <header className="panel-head">
        <h2>{title}</h2>
        {action}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function MetaGrid({ items }: { items: Array<{ label: string; value: ReactNode }> }) {
  return (
    <dl className="meta-grid">
      {items.map((item) => (
        <div key={item.label} className="meta-item">
          <dt>{item.label}</dt>
          <dd>{item.value || <EmptyValue />}</dd>
        </div>
      ))}
    </dl>
  );
}

export function BulletList({ items }: { items: string[] }) {
  if (items.length === 0) return <EmptyValue />;
  return (
    <ul className="stack-list">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

export function PassChip({ passed }: { passed: boolean | null }) {
  if (passed === null) return <span className="chip chip-neutral">No disponible</span>;
  return (
    <span className={passed ? "chip chip-pass" : "chip chip-fail"}>
      {passed ? "passed" : "did not pass"}
    </span>
  );
}

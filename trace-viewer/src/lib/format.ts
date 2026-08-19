export function humanize(value: string | null | undefined): string {
  if (!value) return "No disponible";
  return value.replace(/_/g, " ");
}

export function formatUsd(value: number): string {
  if (!Number.isFinite(value) || value === 0) return "$0.00";
  if (value < 0.01) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(2)}`;
}

export function formatTokens(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

export function formatCount(value: number, singular: string, plural = `${singular}s`): string {
  return `${value} ${value === 1 ? singular : plural}`;
}

export function shortRef(ref: string | null | undefined): string {
  if (!ref) return "No disponible";
  const parts = ref.split(":");
  return parts.length > 2 ? parts.slice(-2).join(":") : ref;
}

export function formatMetric(value: unknown): string {
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "No disponible";
    return Number.isInteger(value) ? String(value) : value.toFixed(3);
  }
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "string") return value;
  return "";
}

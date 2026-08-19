import type { ConflictNodeReport, PipelineTrace } from "../types/trace";
import { humanize } from "./format";

export interface Explanation {
  headline: string;
  bullets: string[];
}

function nodeLabel(node: ConflictNodeReport | undefined, fallback: string): string {
  if (!node) return fallback;
  const candidate = node.candidate;
  if (candidate) {
    return `${node.id} (${candidate.process} at ${candidate.site})`;
  }
  return `${node.id} (${node.state.node_type})`;
}

export function explainTrace(trace: PipelineTrace): Explanation {
  const byId = new Map(trace.tree.nodes.map((node) => [node.id, node]));
  const selectedId = trace.post_graph.selected_id;
  const selected = selectedId ? byId.get(selectedId) : undefined;
  const failed = trace.tree.nodes.filter((node) => node.state.status === "fail");
  const degraded = trace.tree.nodes.filter((node) => node.state.status === "degraded");
  const discardedSurvivors = trace.tree.surviving_ids.filter((id) => id !== selectedId);
  const bullets: string[] = [];

  if (selectedId) {
    bullets.push(`Selected branch: ${nodeLabel(selected, selectedId)}.`);
  } else {
    bullets.push("No selected_id is present in post_graph.");
  }

  if (trace.tree.surviving_ids.length > 0) {
    bullets.push(`Surviving nodes: ${trace.tree.surviving_ids.join(", ")}.`);
  }

  if (discardedSurvivors.length > 0) {
    bullets.push(
      `Survived the walk but were not selected: ${discardedSurvivors
        .map((id) => nodeLabel(byId.get(id), id))
        .join("; ")}.`,
    );
  }

  if (failed.length > 0) {
    bullets.push(
      `Failed nodes: ${failed.map((node) => nodeLabel(node, node.id)).join("; ")}.`,
    );
  }

  if (degraded.length > 0) {
    bullets.push(
      `Degraded nodes: ${degraded.map((node) => nodeLabel(node, node.id)).join("; ")}.`,
    );
  }

  if (trace.judge) {
    if (trace.judge.resolution) {
      bullets.push(`Judge resolution: ${trace.judge.resolution}`);
    }
    for (const finding of trace.judge.findings) {
      bullets.push(`Finding (${humanize(finding.kind)}): ${finding.description}`);
    }
    for (const gap of trace.judge.gaps) {
      bullets.push(`Gap: ${gap}`);
    }
  }

  for (const conflict of trace.verdict.conflicts) {
    bullets.push(`Conflict (${humanize(conflict.kind)}): ${conflict.description}`);
  }

  const citations = trace.judge?.citations ?? [];
  if (citations.length > 0) {
    const refs = citations
      .map((item) => item.ref)
      .filter((item): item is string => Boolean(item));
    if (refs.length > 0) {
      bullets.push(`Citations: ${refs.join(", ")}.`);
    }
  }

  const headline = [
    `${trace.request_id} was judged ${humanize(trace.verdict.verdict)}`,
    `with ${humanize(trace.verdict.confidence)} confidence`,
  ].join(" ");

  return { headline, bullets };
}

export function modifiedSites(trace: PipelineTrace): Set<string> {
  const sites = new Set<string>();
  for (const modification of trace.request.modifications) {
    sites.add(modification.site);
  }
  for (const entry of trace.verdict.site_map) {
    sites.add(entry.resolved);
    sites.add(entry.requested);
  }
  return sites;
}

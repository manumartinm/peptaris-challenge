import { formatMetric, humanize } from "../../lib/format";
import { isRecord } from "../../lib/guards";
import type {
  CandidateMolecularValidation,
  CandidatePostGraphResult,
  JsonObject,
  PipelineTrace,
} from "../../types/trace";
import { MoleculeViewer } from "../MoleculeViewer";
import { BulletList, EmptyValue, MetaGrid, Section, StatusChip } from "../ui";
import { CandidateLabel, CostLine } from "./shared";

function MetricList({ value, omit }: { value: unknown; omit?: string[] }) {
  if (!isRecord(value)) return <EmptyValue />;
  const hidden = new Set(omit ?? []);
  const entries = Object.entries(value).filter(([key, item]) => {
    if (hidden.has(key)) return false;
    if (item == null) return false;
    if (typeof item === "object") return false;
    return true;
  });
  if (entries.length === 0) return <EmptyValue />;
  return (
    <ul className="kv-list">
      {entries.map(([key, item]) => (
        <li key={key}>
          <code>{humanize(key)}</code>
          <span>{formatMetric(item)}</span>
        </li>
      ))}
    </ul>
  );
}

function skipReason(unknowns: string[]): string | null {
  const hit = unknowns.find((item) => item.startsWith("boltz_skipped:"));
  return hit ? hit.slice("boltz_skipped:".length) : null;
}

function issueRecords(value: unknown): JsonObject[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord);
}

function Structure3D({
  ensemble,
  unknowns,
}: {
  ensemble: JsonObject | null;
  unknowns: string[];
}) {
  if (!ensemble) {
    const reason = skipReason(unknowns);
    return (
      <div className="stack">
        <p>No 3D — Boltz skipped</p>
        {reason ? <p>{humanize(reason)}</p> : null}
      </div>
    );
  }
  const issues = issueRecords(ensemble.issues);
  if (ensemble.embedding_ok !== true) {
    const first = issues[0];
    return (
      <div className="stack">
        <StatusChip status="fail" />
        {first?.code ? <code>{String(first.code)}</code> : null}
        {first?.message ? <p>{String(first.message)}</p> : null}
      </div>
    );
  }
  const sequenceOnly = issues.some((item) => item.code === "boltz_sequence_only");
  const cif = typeof ensemble.cif === "string" ? ensemble.cif : "";
  return (
    <div className="stack">
      {cif ? <MoleculeViewer cif={cif} /> : null}
      <MetaGrid
        items={[
          { label: "Predicted", value: "yes" },
          { label: "Confident", value: ensemble.converged ? "yes" : "no" },
          {
            label: "Structure confidence",
            value:
              typeof ensemble.structure_confidence === "number"
                ? formatMetric(ensemble.structure_confidence)
                : null,
          },
          {
            label: "pTM",
            value: typeof ensemble.ptm === "number" ? formatMetric(ensemble.ptm) : null,
          },
          {
            label: "Complex pLDDT",
            value:
              typeof ensemble.complex_plddt === "number"
                ? formatMetric(ensemble.complex_plddt)
                : null,
          },
          { label: "Source", value: "boltz" },
        ]}
      />
      {sequenceOnly ? <p>Backbone only; PTMs were not sent to Boltz.</p> : null}
    </div>
  );
}

function MolecularCard({
  molecular,
}: {
  molecular: CandidateMolecularValidation;
}) {
  const twoD = molecular.two_d;
  const recipe = isRecord(molecular.recipe) ? molecular.recipe : null;

  return (
    <div className="stack">
      <Section title="2D validation">
        {twoD ? (
          <>
            <MetaGrid
              items={[
                { label: "Valid", value: twoD.valid ? "yes" : "no" },
                { label: "Formula", value: twoD.formula },
                {
                  label: "Exact MW",
                  value: twoD.exact_mw != null ? `${twoD.exact_mw.toFixed(3)} Da` : null,
                },
                { label: "Issues", value: String(twoD.issues.length) },
              ]}
            />
            {twoD.smiles ? <pre className="smiles">{twoD.smiles}</pre> : <EmptyValue />}
            {twoD.issues.length > 0 ? (
              <pre className="mini-json">{JSON.stringify(twoD.issues, null, 2)}</pre>
            ) : null}
          </>
        ) : (
          <EmptyValue />
        )}
      </Section>

      <Section title="Descriptors">
        <MetricList value={molecular.descriptors} />
      </Section>
      <Section title="3D structure">
        <Structure3D ensemble={molecular.ensemble} unknowns={molecular.unknowns} />
      </Section>

      <Section title="Recipe">
        {recipe ? (
          <>
            <MetaGrid
              items={[
                { label: "Sequence", value: typeof recipe.sequence === "string" ? recipe.sequence : null },
                { label: "N-terminus", value: humanize(typeof recipe.n_terminus === "string" ? recipe.n_terminus : null) },
                { label: "C-terminus", value: humanize(typeof recipe.c_terminus === "string" ? recipe.c_terminus : null) },
              ]}
            />
            <h3 className="inline-heading">Bonds</h3>
            {Array.isArray(recipe.bonds) && recipe.bonds.length > 0 ? (
              <ul className="stack-list">
                {recipe.bonds.map((bond, index) => {
                  if (!isRecord(bond)) return null;
                  return (
                    <li key={index}>
                      {String(bond.from_atom)} → {String(bond.to_fragment)} · {String(bond.bond_type)}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <EmptyValue />
            )}
            <h3 className="inline-heading">Fragments</h3>
            {molecular.fragments.length > 0 ? (
              <ul className="stack-list">
                {molecular.fragments.map((fragment, index) => {
                  if (!isRecord(fragment)) return null;
                  return (
                    <li key={String(fragment.instance_id ?? index)}>
                      {String(fragment.instance_id ?? "fragment")}
                      {fragment.catalog_id ? ` · ${String(fragment.catalog_id)}` : ""}
                      {fragment.site ? ` at ${String(fragment.site)}` : ""}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <EmptyValue />
            )}
          </>
        ) : (
          <EmptyValue />
        )}
      </Section>

      <Section title="Unknowns">
        <BulletList items={molecular.unknowns} />
      </Section>
    </div>
  );
}

function CandidateMolecular({
  item,
  selectedId,
  tiedIds,
}: {
  item: CandidatePostGraphResult;
  selectedId: string | null;
  tiedIds: string[];
}) {
  return (
    <article className="candidate-card">
      <CandidateLabel
        nodeId={item.node_id}
        candidate={item.candidate}
        selected={item.node_id === selectedId}
        tied={tiedIds.includes(item.node_id)}
      />
      {item.molecular ? (
        <MolecularCard molecular={item.molecular} />
      ) : (
        <EmptyValue />
      )}
    </article>
  );
}

export function MolecularView({ trace }: { trace: PipelineTrace }) {
  const report = trace.post_graph;
  return (
    <div className="view-stack">
      <Section title="Post-graph molecular validation">
        <MetaGrid
          items={[
            { label: "Selected", value: report.selected_id },
            { label: "Surviving", value: report.surviving_ids.join(", ") },
            { label: "Tied", value: report.tied_ids.join(", ") || null },
            { label: "Candidates", value: String(report.candidates.length) },
          ]}
        />
        <CostLine cost={trace.cost.phases.post_graph} />
        <BulletList items={report.unknowns} />
      </Section>
      {report.candidates.length === 0 ? (
        <EmptyValue />
      ) : (
        report.candidates.map((item) => (
          <CandidateMolecular
            key={item.node_id}
            item={item}
            selectedId={report.selected_id}
            tiedIds={report.tied_ids}
          />
        ))
      )}
    </div>
  );
}

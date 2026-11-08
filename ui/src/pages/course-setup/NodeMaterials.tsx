import { useCallback, useEffect, useState } from "react";
import { Button } from "../../components/Button";
import {
  decideMaterial,
  nodeMaterials,
  nodeSources,
  pageRanges,
  type MaterialFile,
  type RankedSource,
} from "../../api/materials";

/** S6 sources of one roadmap node (spec 12.1, #114): the learner's own pages first,
 * suggestions waiting for one tap, then verified catalog sources. */
export function NodeMaterials({ nodeId }: { nodeId: string }) {
  const [sources, setSources] = useState<RankedSource[] | null>(null);
  const [suggested, setSuggested] = useState<MaterialFile[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [ranked, files] = await Promise.all([nodeSources(nodeId), nodeMaterials(nodeId)]);
      setSources(ranked.sources);
      setSuggested(files.filter((f) => f.status === "suggested"));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load sources.");
    }
  }, [nodeId]);

  useEffect(() => {
    void load();
  }, [load]);

  const decide = async (file: MaterialFile, attached: boolean) => {
    setBusy(true);
    try {
      await decideMaterial(nodeId, file, attached);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save your answer.");
    } finally {
      setBusy(false);
    }
  };

  if (error) return <p role="alert" className="row-error">{error}</p>;
  if (sources === null) return <p className="core-field-label">Loading sources…</p>;
  const own = sources.filter((s) => s.kind === "user_material");
  const catalog = sources.filter((s) => s.kind !== "user_material");
  return (
    <div className="core-node-sources" aria-label="Learning sources">
      {own.length > 0 && (
        <ul className="core-own-material">
          {own.map((s) => (
            <li key={s.id}>
              <span className="core-own-badge">{s.reason}</span>
              <strong>{s.title}</strong>
              <span> · pages {pageRanges(s.pages)}</span>
            </li>
          ))}
        </ul>
      )}
      {suggested.map((file) => (
        <div className="core-material-suggestion" key={file.file_name}>
          <p>
            Is <strong>{file.file_name}</strong>, pages{" "}
            {pageRanges(file.pages.map((p) => p.page))}, about this step?
          </p>
          <Button primary disabled={busy} onClick={() => void decide(file, true)}>
            Yes, attach
          </Button>
          <Button disabled={busy} onClick={() => void decide(file, false)}>
            No
          </Button>
        </div>
      ))}
      {catalog.length > 0 && (
        <ul className="core-catalog-sources">
          {catalog.map((s) => (
            <li key={s.id}>
              {s.url ? (
                <a href={s.url} target="_blank" rel="noreferrer">
                  {s.title}
                </a>
              ) : (
                s.title
              )}
              <span> · {s.provider}</span>
            </li>
          ))}
        </ul>
      )}
      {sources.length === 0 && suggested.length === 0 && (
        <p className="core-field-label">No sources for this step yet.</p>
      )}
    </div>
  );
}

import { Button } from "../../components/Button";
import { Modal } from "../../components/Modal";
import type { RoadmapNode } from "../../api/types";
import { NodeMaterials } from "./NodeMaterials";
export function StageDetails({
  node,
  live,
  onClose,
  onOpenMaterialPage,
  onSchedule,
}: {
  node: RoadmapNode & { outcome_ids?: string[] };
  live: boolean;
  onClose: () => void;
  onOpenMaterialPage?: (sourceId: string, page: number) => void;
  onSchedule?: () => void;
}) {
  return (
    <Modal title={`Stage page · ${node.title}`} onClose={onClose}>
      <div className="core-stage-details">
        <p>
          Week {node.week ?? "—"} ·{" "}
          {node.est_minutes ?? node.duration_minutes ?? "—"} min
        </p>
        {node.outcome_ids?.length ? (
          <p>Learning outcomes: {node.outcome_ids.join(", ")}</p>
        ) : null}
        {live ? (
          <NodeMaterials
            nodeId={node.id}
            onOpenMaterialPage={onOpenMaterialPage}
          />
        ) : (
          <p>
            Live learning sources require a backend connection. Preview mode
            does not include verified sources.
          </p>
        )}
        {onSchedule && (
          <Button primary onClick={onSchedule}>
            Schedule roadmap (S7)
          </Button>
        )}
      </div>
    </Modal>
  );
}

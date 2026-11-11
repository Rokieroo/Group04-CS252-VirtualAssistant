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
    <Modal title={`Trang chặng · ${node.title}`} onClose={onClose}>
      <div className="core-stage-details">
        <p>
          Tuần {node.week ?? "—"} ·{" "}
          {node.est_minutes ?? node.duration_minutes ?? "—"} phút
        </p>
        {node.outcome_ids?.length ? (
          <p>Chuẩn đầu ra: {node.outcome_ids.join(", ")}</p>
        ) : null}
        {live ? (
          <NodeMaterials
            nodeId={node.id}
            onOpenMaterialPage={onOpenMaterialPage}
          />
        ) : (
          <p>
            Nguồn học thực cần kết nối backend. Bản xem trước không có nguồn
            được xác minh.
          </p>
        )}
        {onSchedule && (
          <Button primary onClick={onSchedule}>
            Xếp lịch lộ trình (S7)
          </Button>
        )}
      </div>
    </Modal>
  );
}

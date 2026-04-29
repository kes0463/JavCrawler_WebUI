import { Download } from "lucide-react";

import { sleep } from "@/lib/utils";
import { useAsync } from "@/hooks/useAsync";
import { ActionButton } from "@/components/ui/ActionButton";

const simulateAction = () => sleep(1800);

export function ButtonShowcase() {
  const primaryAction = useAsync(simulateAction);
  const downloadAction = useAsync(simulateAction);

  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap gap-2">
        <ActionButton
          variant="primary"
          loading={primaryAction.loading}
          onClick={primaryAction.execute}
        >
          {primaryAction.loading ? "처리 중..." : "실행"}
        </ActionButton>
        <ActionButton variant="secondary">보조</ActionButton>
        <ActionButton variant="ghost">고스트</ActionButton>
      </div>
      <div className="flex flex-wrap gap-2">
        <ActionButton
          variant="outline"
          loading={downloadAction.loading}
          icon={<Download className="w-3.5 h-3.5" />}
          onClick={downloadAction.execute}
        >
          내보내기
        </ActionButton>
        <ActionButton variant="danger">삭제</ActionButton>
        <ActionButton variant="secondary" disabled>비활성</ActionButton>
      </div>
    </div>
  );
}

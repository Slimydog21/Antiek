import { Suspense, lazy } from "react";
import type { OwnerModelController } from "../../hooks/useOwnerModelController";
export interface OwnerModelUsagePickerProps {
  controller: OwnerModelController;
  triggerAriaLabel?: string;
  allowHouse: boolean;
  isResourceCurrent?: () => boolean;
}
const Impl = lazy(() => import("./OwnerModelUsagePicker.impl"));
export default function OwnerModelUsagePicker(
  props: OwnerModelUsagePickerProps,
) {
  return (
    <Suspense fallback={null}>
      <Impl {...props} />
    </Suspense>
  );
}

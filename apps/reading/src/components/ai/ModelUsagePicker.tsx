import { Suspense, lazy } from "react";
import type { ModelUsagePickerProps } from "./ModelUsagePicker.impl";

export type { ModelUsagePickerProps } from "./ModelUsagePicker.impl";

// Seven surfaces mount this control, two of them in the eager app shell
// (AISidecar, CommandPalette). A static import from the shell pins the whole
// picker — its enrichment table, badges and dropdown — into the entry chunk,
// which is what pushed the S12 WP-12.2 entry 348 B over its 700 KB gzipped
// ceiling while a mis-aimed gate stayed green. Splitting once here, at the
// module boundary every importer already uses, moves it out of the entry for
// all seven surfaces without touching their imports.
const ModelUsagePickerImpl = lazy(() => import("./ModelUsagePicker.impl"));

export default function ModelUsagePicker(props: ModelUsagePickerProps) {
  return (
    <Suspense fallback={null}>
      <ModelUsagePickerImpl {...props} />
    </Suspense>
  );
}

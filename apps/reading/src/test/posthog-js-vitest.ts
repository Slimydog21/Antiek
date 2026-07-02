type Property =
  | string
  | number
  | boolean
  | null
  | undefined
  | Property[]
  | { [key: string]: Property };
type Properties = Record<string, Property>;
type CaptureResult = {
  event?: string;
  properties?: Properties;
  $set?: Properties;
  $set_once?: Properties;
  [key: string]: unknown;
};
type BeforeSendFn = (event: CaptureResult | null) => CaptureResult | null;

const posthog = {
  init: () => undefined,
  capture: (_event: string, _properties?: Properties) => undefined,
  captureException: (_error: unknown, _properties?: Properties) => undefined,
  identify: (_id: string, _properties?: Properties) => undefined,
  reset: () => undefined,
};

export default posthog;
export type { BeforeSendFn, CaptureResult, Properties, Property };

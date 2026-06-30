declare module "katex" {
  export interface KatexOptions {
    displayMode?: boolean;
    throwOnError?: boolean;
    strict?: boolean | "ignore" | "warn" | "error";
    output?: "html" | "mathml" | "htmlAndMathml";
    errorColor?: string;
    maxExpand?: number;
  }

  export function renderToString(tex: string, options?: KatexOptions): string;
}

import { readdirSync, readFileSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { join, relative } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");
function files(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? files(path)
      : /\.[cm]?[jt]sx?$/.test(path) && !/\.(test|spec|stories)\./.test(path) ? [path] : [];
  });
}

/** AST plus native target types, rather than a spelling census. Element/React
 * handlers are explicitly outside the global registration population. */
export function undeclaredRegistrations(sources: string[]): string[] {
  const program = ts.createProgram(sources, { allowJs: true, jsx: ts.JsxEmit.ReactJSX, skipLibCheck: true });
  const checker = program.getTypeChecker();
  const errors: string[] = [];
  for (const path of sources) {
    const file = program.getSourceFile(path);
    if (!file) continue;
    const rel = relative(SRC, path);
    const nativeSeam = rel === "workspace/keyboardOwnership.ts";
    function globalTarget(node: ts.Node, visited = new Set<ts.Node>()): boolean {
      if (visited.has(node)) return false;
      visited.add(node);
      const text = node.getText(file);
      if (["window", "document", "globalThis"].includes(text)) return true;
      const symbol = checker.getSymbolAtLocation(node);
      const declaration = symbol?.valueDeclaration;
      if (declaration && ts.isVariableDeclaration(declaration) && declaration.initializer
        && /\.content(Document|Window)$/.test(declaration.initializer.getText(file))) return false;
      if (declaration && ts.isVariableDeclaration(declaration) && declaration.initializer && globalTarget(declaration.initializer, visited)) return true;
      return /\b(Window|Document|typeof globalThis)\b/.test(checker.typeToString(checker.getTypeAtLocation(node)));
    }
    function literal(node: ts.Expression): string | undefined {
      if (ts.isAsExpression(node) || ts.isParenthesizedExpression(node)) return literal(node.expression);
      if (ts.isStringLiteralLike(node)) return node.text;
      if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.PlusToken) {
        const left = literal(node.left), right = literal(node.right);
        if (left !== undefined && right !== undefined) return left + right;
      }
      const type = checker.getTypeAtLocation(node);
      return type.isStringLiteral() ? type.value : undefined;
    }
    function fail(node: ts.Node, detail: string) {
      errors.push(`${path}:${file!.getLineAndCharacterOfPosition(node.getStart(file)).line + 1} ${detail}`);
    }
    function visit(node: ts.Node) {
      if (!nativeSeam && (ts.isPropertyAccessExpression(node) || ts.isElementAccessExpression(node)) && globalTarget(node.expression)) {
        const name = ts.isPropertyAccessExpression(node) ? node.name.text : node.argumentExpression && literal(node.argumentExpression);
        if (name === "addEventListener" && !(ts.isCallExpression(node.parent) && node.parent.expression === node)) {
          fail(node, "undeclared-keyboard-registration: global listener reference escapes the checked registration seam");
        }
      }
      if (!nativeSeam && ts.isVariableDeclaration(node) && ts.isObjectBindingPattern(node.name) && node.initializer && globalTarget(node.initializer)) {
        if (node.name.elements.some((el) => (el.propertyName ?? el.name).getText(file) === "addEventListener")) fail(node, "undeclared-keyboard-registration: destructured global listener");
      }
      if (!nativeSeam && ts.isCallExpression(node)) {
        const fn = node.expression;
        if ((ts.isPropertyAccessExpression(fn) || ts.isElementAccessExpression(fn)) && globalTarget(fn.expression)) {
          const name = ts.isPropertyAccessExpression(fn) ? fn.name.text : fn.argumentExpression && literal(fn.argumentExpression);
          if (name === "addEventListener") {
            const event = node.arguments[0] && literal(node.arguments[0]);
            if (event === undefined || /^key(down|up|press)$/.test(event)) fail(node, `undeclared-keyboard-registration ${event ?? "dynamic event"}; use registerKeyboardOwner with id/scope/eligible`);
          }
        }
        if (ts.isIdentifier(fn) && fn.text === "registerKeyboardOwner") {
          const meta = node.arguments[1];
          if (!meta || !ts.isObjectLiteralExpression(meta)) fail(node, "keyboard owner requires explicit id/scope/eligible metadata");
          else for (const name of ["id", "scope", "eligible"]) {
            if (!meta.properties.some((p) => p.name?.getText(file) === name)) fail(node, `keyboard owner missing ${name}`);
          }
        }
      }
      if (!nativeSeam && ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
        const lhs = node.left;
        if ((ts.isPropertyAccessExpression(lhs) || ts.isElementAccessExpression(lhs)) && globalTarget(lhs.expression)) {
          const name = ts.isPropertyAccessExpression(lhs) ? lhs.name.text : lhs.argumentExpression && literal(lhs.argumentExpression);
          if (name && /^onkey/.test(name)) fail(node, `undeclared-keyboard-registration ${name}`);
        }
      }
      ts.forEachChild(node, visit);
    }
    visit(file);
  }
  return errors;
}

describe("declared global keyboard registrations", () => {
  it("rejects undeclared native registration, including aliases and property assignment", () => {
    expect(undeclaredRegistrations(files(SRC))).toEqual([]);
  }, 20_000);
  it.each([
    'window.addEventListener("keydown", () => {});',
    'const root: any = window; const event = "key" + "down"; root["addEvent" + "Listener"](event, () => {});',
    'globalThis["on" + "keydown"] = () => {};',
    'const listen = window.addEventListener.bind(window); listen("keydown", () => {});',
    'const { addEventListener: listen } = window; listen("keydown", () => {});',
  ])("rejects undeclared spelling %s", (source) => {
    const dir = mkdtempSync(join(SRC, ".keyboard-census-"));
    const file = join(dir, "probe.ts");
    try {
      writeFileSync(file, source);
      expect(undeclaredRegistrations([file]).join("\n")).toContain("undeclared-keyboard-registration");
    } finally { rmSync(dir, { recursive: true, force: true }); }
  });

  it("the dispatcher installs exactly one prefix owner and one direct owner", () => {
    const source = readFileSync(join(SRC, "workspace/shortcuts.ts"), "utf8");
    for (const id of ["workspace.prefix", "workspace.direct"]) {
      expect(source.split(`id: "${id}"`).length - 1, `owner ${id}: dispatcher installation missing or duplicated`).toBe(1);
    }
  });
});

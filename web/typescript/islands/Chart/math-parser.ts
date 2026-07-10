import { parse, isSymbolNode, type EvalFunction } from "mathjs/number";

const ALLOWED_IDENTIFIERS = new Set([
  "x",
  "pi",
  "e",
  "sin",
  "cos",
  "tan",
  "asin",
  "acos",
  "atan",
  "sqrt",
  "abs",
  "exp",
  "log",
  "log10",
  "floor",
  "ceil",
  "round",
  "min",
  "max",
]);

const ALLOWED_NODE_TYPES = new Set([
  "OperatorNode",
  "ConstantNode",
  "SymbolNode",
  "FunctionNode",
  "ParenthesisNode",
]);

export function compileExpression(source: string): EvalFunction {
  if (source.length > 300) {
    throw new Error("Formula too long");
  }

  let nodes = 0;
  const expression = parse(source);
  expression.traverse((node) => {
    nodes += 1;
    if (nodes >= 100) {
      throw new Error("Formula too complex");
    }

    if (!ALLOWED_NODE_TYPES.has(node.type)) {
      throw new Error(`Unsupported expression type: ${node.type}`);
    }

    if (isSymbolNode(node) && !ALLOWED_IDENTIFIERS.has(node.name)) {
      throw new Error(`Unsupported identifier: ${node.name}`);
    }
  });

  return expression.compile();
}

export function sampleExpression(
  evaluate: EvalFunction,
  min: number,
  max: number,
  count = 512,
): Array<[number, number | null]> {
  return Array.from({ length: count }, (_, index) => {
    const x = min + ((max - min) * index) / (count - 1);
    const result = evaluate.evaluate({ x });
    const y = Number(result);
    return [x, Number.isFinite(y) ? y : null];
  });
}

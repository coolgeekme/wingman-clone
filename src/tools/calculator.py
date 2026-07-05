import ast
import operator
from src.tools.base import BaseTool, ToolResult

SAFE_OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg}

def safe_eval(expr: str) -> float:
    tree = ast.parse(expr, mode="eval")
    def _eval(node):
        if isinstance(node, ast.Expression): return _eval(node.body)
        elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)): return node.value
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in SAFE_OPERATORS: raise ValueError(f"Unsupported operator: {op_type.__name__}")
            return SAFE_OPERATORS[op_type](_eval(node.left), _eval(node.right))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub): return -_eval(node.operand)
        else: raise ValueError(f"Unsupported expression: {ast.dump(node)}")
    return _eval(tree)

class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluate a mathematical expression. Supports +, -, *, /, **."
    parameters = {"type": "object", "properties": {"expression": {"type": "string", "description": "Math expression to evaluate"}}, "required": ["expression"]}

    async def execute(self, **kwargs) -> ToolResult:
        expression = kwargs.get("expression", "")
        try:
            result = safe_eval(expression)
            return ToolResult(success=True, data={"expression": expression, "result": result})
        except (ValueError, SyntaxError, TypeError, ZeroDivisionError) as e:
            return ToolResult(success=False, error=f"Cannot evaluate '{expression}': {e}")

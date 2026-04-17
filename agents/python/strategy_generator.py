from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

import orjson
import pandas as pd

from agents.python.backtest import run_backtest
from config.settings import settings
from core import llm_client

GENERATOR_SYSTEM = """You are a quantitative strategy developer.
You must output ONLY Python code for a pure function with this exact signature:

def strategy(df: pd.DataFrame, i: int) -> str:
    # df has columns: timestamp, open, high, low, close, volume
    # i is the current index; use df.iloc[:i+1] for past data
    # return exactly one of: "buy", "sell", or "hold"
    ...

Rules:
- NO imports, NO print, NO I/O
- Access only pandas operations and basic math
- Must handle short data (return "hold" if i < 30)
- Use standard technical logic: RSI, MA crossovers, price action, volume spikes
- Keep it concise (under 40 lines)

Output: Just the function code. No explanation, no markdown fences."""


_FORBIDDEN_CALLS = {
    "open",
    "exec",
    "eval",
    "compile",
    "__import__",
    "input",
    "globals",
    "locals",
    "getattr",
    "setattr",
    "delattr",
}


@dataclass
class GeneratedStrategy:
    code: str = ""
    name: str = ""
    backtest_summary: dict = field(default_factory=dict)
    valid: bool = False
    error: str = ""


def _validate_ast(code: str) -> tuple[bool, str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"syntax error: {e}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            return False, "imports not allowed"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALLS:
            return False, f"forbidden call: {node.func.id}"
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return False, f"dunder access not allowed: {node.attr}"

    if "def strategy" not in code:
        return False, "missing strategy function"

    return True, ""


def _extract_code(response: str) -> str:
    fence_match = re.search(r"```(?:python)?\s*(.*?)```", response, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    lines = response.split(chr(10))
    code_lines = []
    started = False
    for line in lines:
        if line.startswith("def strategy"):
            started = True
        if started:
            code_lines.append(line)
    return chr(10).join(code_lines).strip() if code_lines else response.strip()


def _run_sandbox(code: str):
    import math

    safe_builtins = {
        "len": len,
        "min": min,
        "max": max,
        "abs": abs,
        "range": range,
        "sum": sum,
        "int": int,
        "float": float,
        "round": round,
        "True": True,
        "False": False,
        "None": None,
    }
    sandbox = {"pd": pd, "math": math, "__builtins__": safe_builtins}
    runner = compile(code, "<ai_strategy>", "exec")
    eval(runner, sandbox)
    return sandbox.get("strategy")


async def generate_strategy(notes: str = "") -> GeneratedStrategy:
    prompt = notes or "Generate a novel swing trading strategy using price action, RSI, and moving averages."
    response = await llm_client.query(prompt, system=GENERATOR_SYSTEM, temperature=0.7, max_tokens=800)

    code = _extract_code(response)
    valid, error = _validate_ast(code)

    result = GeneratedStrategy(code=code, valid=valid, error=error)
    if not valid:
        return result

    try:
        _run_sandbox(code)
        result.valid = True
    except Exception as e:
        result.valid = False
        result.error = f"compile failed: {e}"

    return result


async def generate_and_backtest(symbols: list[str] | None = None, period: str = "1y") -> GeneratedStrategy:
    gen = await generate_strategy()
    if not gen.valid:
        return gen

    syms = symbols or settings.symbols[:5]
    strategy_fn = _run_sandbox(gen.code)

    class _CustomStrategy:
        name = "ai_generated"

        def signal(self, df: pd.DataFrame, i: int) -> str:
            try:
                r = strategy_fn(df, i)
                if r in ("buy", "sell", "hold"):
                    return r
                return "hold"
            except Exception:
                return "hold"

    from agents.strategies import base

    original_get = base.get_strategy
    try:
        base.get_strategy = lambda name: _CustomStrategy()
        result = run_backtest(syms, initial_capital=100_000.0, period=period, strategy_name="ai_generated")
        gen.backtest_summary = result.summary()
        gen.name = f"ai_gen_{hash(gen.code) % 10000:04d}"
    except Exception as e:
        gen.error = f"backtest failed: {e}"
        gen.valid = False
    finally:
        base.get_strategy = original_get

    return gen


def save_strategy(strategy: GeneratedStrategy) -> Path:
    lib_dir = settings.data_dir / "generated_strategies"
    lib_dir.mkdir(parents=True, exist_ok=True)
    file_path = lib_dir / f"{strategy.name}.json"
    file_path.write_bytes(
        orjson.dumps(
            {
                "name": strategy.name,
                "code": strategy.code,
                "backtest": strategy.backtest_summary,
            },
            option=orjson.OPT_INDENT_2,
        )
    )
    return file_path


def load_saved_strategies() -> list[dict]:
    lib_dir = settings.data_dir / "generated_strategies"
    if not lib_dir.exists():
        return []
    strategies = []
    for f in sorted(lib_dir.glob("*.json")):
        try:
            strategies.append(orjson.loads(f.read_bytes()))
        except Exception:
            continue
    return strategies

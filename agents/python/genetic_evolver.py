from __future__ import annotations

import contextlib
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import orjson

from agents.python.strategy_generator import (
    _extract_code,
    _run_sandbox,
    _validate_ast,
)
from config.settings import settings
from core import llm_client

MUTATE_SYSTEM = """You are a quant strategy engineer. Given an existing trading strategy, produce a MUTATED variant.
Output ONLY the new Python function. Same signature: def strategy(df, i) -> str.
Rules:
- Change 1-2 parameters or thresholds
- Keep the core logic intact
- No imports, no I/O, no dunder access
- Return "buy", "sell", or "hold" only"""

CROSSOVER_SYSTEM = """You are a quant strategy engineer. Given TWO strategies, produce a child that combines their best ideas.
Output ONLY the new Python function. Same signature: def strategy(df, i) -> str.
Rules:
- Combine signal logic from both parents
- No imports, no I/O, no dunder access
- Return "buy", "sell", or "hold" only"""


@dataclass
class Individual:
    code: str = ""
    fitness: float = 0.0
    name: str = ""
    backtest: dict = field(default_factory=dict)
    generation: int = 0
    parent_names: list[str] = field(default_factory=list)


def _fitness_score(backtest_summary: dict) -> float:
    if not backtest_summary:
        return 0.0

    sharpe = backtest_summary.get("sharpe_ratio", 0)
    pnl_pct = backtest_summary.get("total_pnl_pct", 0)
    dd = backtest_summary.get("max_drawdown", 0) or 1
    trades = backtest_summary.get("total_trades", 0)

    if trades < 3:
        return pnl_pct * 0.1

    risk_adjusted = pnl_pct / max(dd, 5)
    return round(sharpe * 10 + risk_adjusted, 3)


def _strategy_name(code: str, generation: int) -> str:
    h = hashlib.md5(code.encode()).hexdigest()[:6]
    return f"gen{generation:02d}_{h}"


async def _mutate(parent: Individual) -> str | None:
    prompt = "Original strategy:" + chr(10) + parent.code + chr(10) + chr(10) + "Generate a MUTATED variant."
    response = await llm_client.query(prompt, system=MUTATE_SYSTEM, temperature=0.9, max_tokens=800)
    code = _extract_code(response)
    valid, _ = _validate_ast(code)
    if not valid:
        return None
    try:
        _run_sandbox(code)
        return code
    except Exception:
        return None


async def _crossover(parent_a: Individual, parent_b: Individual) -> str | None:
    prompt = (
        "Parent A:"
        + chr(10)
        + parent_a.code
        + chr(10)
        + chr(10)
        + "Parent B:"
        + chr(10)
        + parent_b.code
        + chr(10)
        + chr(10)
        + "Generate a CHILD combining both."
    )
    response = await llm_client.query(prompt, system=CROSSOVER_SYSTEM, temperature=0.8, max_tokens=800)
    code = _extract_code(response)
    valid, _ = _validate_ast(code)
    if not valid:
        return None
    try:
        _run_sandbox(code)
        return code
    except Exception:
        return None


def _backtest_individual(code: str, symbols: list[str]) -> dict:
    from agents.python.backtest import run_backtest
    from agents.strategies import base

    strategy_fn = _run_sandbox(code)

    class _Candidate:
        name = "evolved"

        def signal(self, df, i):
            try:
                r = strategy_fn(df, i)
                return r if r in ("buy", "sell", "hold") else "hold"
            except Exception:
                return "hold"

    original = base.get_strategy
    try:
        base.get_strategy = lambda _: _Candidate()
        result = run_backtest(symbols, initial_capital=100_000.0, period="6mo", strategy_name="evolved")
        return result.summary()
    except Exception as e:
        return {"error": str(e)}
    finally:
        base.get_strategy = original


def _pop_dir() -> Path:
    return settings.data_dir / "evolved_strategies"


def _save_individual(ind: Individual) -> None:
    d = _pop_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{ind.name}.json").write_bytes(
        orjson.dumps(
            {
                "code": ind.code,
                "fitness": ind.fitness,
                "name": ind.name,
                "backtest": ind.backtest,
                "generation": ind.generation,
                "parent_names": ind.parent_names,
                "created_at": datetime.now().isoformat(),
            },
            option=orjson.OPT_INDENT_2,
        )
    )


def load_population() -> list[Individual]:
    d = _pop_dir()
    if not d.exists():
        return []
    population = []
    for f in d.glob("*.json"):
        try:
            data = orjson.loads(f.read_bytes())
            population.append(Individual(**{k: v for k, v in data.items() if k not in ("created_at",)}))
        except Exception:
            continue
    return sorted(population, key=lambda x: x.fitness, reverse=True)


async def evolve_generation(target_symbols: list[str] | None = None, size: int = 4) -> dict:
    from agents.python.strategy_generator import generate_strategy

    symbols = target_symbols or settings.symbols[:5]
    population = load_population()

    max_gen = max((p.generation for p in population), default=0)
    next_gen = max_gen + 1

    if len(population) < 2:
        seeds = []
        for _ in range(size):
            gen_result = await generate_strategy()
            if gen_result.valid:
                bt = _backtest_individual(gen_result.code, symbols)
                fitness = _fitness_score(bt)
                ind = Individual(code=gen_result.code, fitness=fitness, backtest=bt, generation=1)
                ind.name = _strategy_name(ind.code, 1)
                _save_individual(ind)
                seeds.append(ind)
        return {"generation": 1, "created": len(seeds), "best_fitness": max((s.fitness for s in seeds), default=0)}

    parents = population[: max(2, size // 2)]
    offspring = []

    for parent in parents[:2]:
        code = await _mutate(parent)
        if code:
            bt = _backtest_individual(code, symbols)
            fitness = _fitness_score(bt)
            child = Individual(code=code, fitness=fitness, backtest=bt, generation=next_gen, parent_names=[parent.name])
            child.name = _strategy_name(child.code, next_gen)
            offspring.append(child)

    if len(parents) >= 2:
        code = await _crossover(parents[0], parents[1])
        if code:
            bt = _backtest_individual(code, symbols)
            fitness = _fitness_score(bt)
            child = Individual(
                code=code,
                fitness=fitness,
                backtest=bt,
                generation=next_gen,
                parent_names=[parents[0].name, parents[1].name],
            )
            child.name = _strategy_name(child.code, next_gen)
            offspring.append(child)

    for ind in offspring:
        _save_individual(ind)

    all_pop = load_population()
    survivors = all_pop[:10]

    for f in _pop_dir().glob("*.json"):
        name = f.stem
        if not any(s.name == name for s in survivors):
            with contextlib.suppress(Exception):
                f.unlink()

    return {
        "generation": next_gen,
        "offspring_created": len(offspring),
        "population_size": len(survivors),
        "best_fitness": survivors[0].fitness if survivors else 0,
        "best_strategy_name": survivors[0].name if survivors else None,
    }

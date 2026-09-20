"""``uv run python -m evals`` — score the agent against the demo stack.

    uv run python -m evals                          # model from .env
    uv run python -m evals --models gpt-5-mini,qwen3-235b
    uv run python -m evals --cases cpu-per-core,remove-all --verbose
    uv run python -m evals --tags edit --out report.json

LLM settings come from the environment / .env like the app's; --models overrides
LLM_MODEL. Prometheus defaults to the compose stack on localhost:9090 and the
knowledge folder to ../knowledge.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.agent.providers import build_provider
from app.config import Settings
from evals.cases import BY_ID, CASES, Case
from evals.harness import Environment, Result, run_all

ROOT = Path(__file__).resolve().parent.parent


def _select(args: argparse.Namespace) -> list[Case]:
    cases = CASES
    if args.cases:
        unknown = [c for c in args.cases.split(",") if c not in BY_ID]
        if unknown:
            sys.exit(f"unknown case ids: {unknown}")
        cases = [BY_ID[c] for c in args.cases.split(",")]
    if args.tags:
        wanted = set(args.tags.split(","))
        cases = [c for c in cases if wanted & set(c.tags)]
    return cases


def _print_table(model: str, results: list[Result], verbose: bool) -> None:
    passed = sum(r.passed for r in results)
    print(f"\n{model}: {passed}/{len(results)} passed")
    print(f"{'case':<24} {'ok':<4} {'iter':>4} {'tools':>5} {'secs':>6}  failures")
    for r in results:
        mark = "ok" if r.passed else "FAIL"
        note = "; ".join(r.failures)[:110]
        line = f"{r.case.id:<24} {mark:<4} {r.iterations:>4} {len(r.tool_calls):>5}"
        print(f"{line} {r.seconds:>6.1f}  {note}")
        if verbose:
            print(f"    tools: {' → '.join(r.tool_calls) or '-'}")
            for p in r.emitted:
                print(f"    panel: {p['type']} “{p['title']}” unit={p.get('unit')}")
                for q in p.get("queries", []):
                    print(f"           {q['expr']}")
            if r.answer:
                print(f"    answer: {r.answer[:300]}")


def _markdown(rows: list[tuple[str, int, int, float, float]]) -> str:
    out = ["| Model | Passed | Avg turns | Avg seconds |", "| --- | --- | --- | --- |"]
    for model, passed, total, turns, secs in rows:
        out.append(f"| `{model}` | {passed}/{total} | {turns:.1f} | {secs:.0f} |")
    return "\n".join(out)


async def main() -> int:
    parser = argparse.ArgumentParser(
        prog="evals", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--models", help="comma-separated; default LLM_MODEL")
    parser.add_argument("--cases", help="comma-separated case ids")
    parser.add_argument("--tags", help="comma-separated tags")
    parser.add_argument("--prometheus", default="http://localhost:9090")
    parser.add_argument("--knowledge", default=str(ROOT.parent / "knowledge"))
    parser.add_argument("--workdir", default=str(ROOT / ".evals"))
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--out", help="write a JSON report here")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    # The app reads .env from its working directory; when run from backend/ take the repo's.
    env_file = next((f for f in (Path(".env"), ROOT.parent / ".env") if f.is_file()), None)
    base = Settings(_env_file=env_file)  # type: ignore[call-arg]
    models = args.models.split(",") if args.models else [base.llm_model or ""]
    if not models[0]:
        sys.exit("no model: set LLM_MODEL or pass --models")
    cases = _select(args)
    knowledge = Path(args.knowledge)
    env = await Environment.create(
        args.prometheus, Path(args.workdir), knowledge if knowledge.is_dir() else None
    )
    metrics = (await env.catalog_builder.status()).metric_count
    print(f"{len(cases)} cases · Prometheus {args.prometheus} · catalog {metrics} metrics")

    report: dict[str, object] = {
        "at": datetime.now(tz=UTC).isoformat(),
        "prometheus": args.prometheus,
        "models": {},
    }
    rows = []
    try:
        for model in models:
            provider = build_provider(base.model_copy(update={"llm_model": model}))
            if provider is None:
                sys.exit("LLM not configured (LLM_BASE_URL / provider settings)")
            results = await run_all(env, provider, cases, concurrency=args.concurrency)
            _print_table(model, results, args.verbose)
            passed = sum(r.passed for r in results)
            turns = sum(r.iterations for r in results) / max(len(results), 1)
            secs = sum(r.seconds for r in results) / max(len(results), 1)
            rows.append((model, passed, len(results), turns, secs))
            report["models"][model] = [  # type: ignore[index]
                {
                    "case": r.case.id,
                    "passed": r.passed,
                    "failures": r.failures,
                    "iterations": r.iterations,
                    "tools": r.tool_calls,
                    "seconds": round(r.seconds, 1),
                    "panels": r.emitted,
                    "answer": r.answer,
                }
                for r in results
            ]
    finally:
        await env.close()

    if len(rows) > 1:
        print("\n" + _markdown(rows))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, default=str))
        print(f"\nreport written to {args.out}")
    return 0 if all(p == t for _, p, t, _, _ in rows) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

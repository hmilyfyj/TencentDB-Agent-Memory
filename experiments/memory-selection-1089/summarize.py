#!/usr/bin/env python3
"""Summarize recorded calls; strict string checks are diagnostics, not a quality ranking."""
from collections import defaultdict
import json
from pathlib import Path
import statistics
import sys


def summarize(rows):
    usage = defaultdict(lambda: {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cached_prompt_tokens": 0})
    timing = defaultdict(list)
    answers = {}
    errors = []
    for row in rows:
        backend, step, result = row["backend"], row["step"], row["result"]
        if step == "wire:completions" and result.get("usage"):
            bucket = usage[backend]
            bucket["calls"] += 1
            for key in ("prompt_tokens", "completion_tokens"):
                bucket[key] += result["usage"].get(key, 0) or 0
            bucket["cached_prompt_tokens"] += (result["usage"].get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
        category = step.split(":")[0]
        if category in ("add", "pipeline", "recall", "answer"):
            timing[backend + ":" + category].append(row["elapsed_s"])
        if step.startswith("answer:"):
            answers[backend + ":" + step] = {"answer": result.get("answer"),
                "missing_strings": [s for s, present in result.get("expected_present", {}).items() if not present],
                "forbidden_in_context": result.get("forbidden_in_context", []),
                "forbidden_in_answer": result.get("forbidden_in_answer", [])}
        if isinstance(result, dict) and result.get("error_type"):
            errors.append({"backend": backend, "step": step, **result})
    return {"reported_llm_usage": dict(usage), "latency_seconds": {
        key: {"n": len(values), "median": round(statistics.median(values), 4),
              "min": min(values), "max": max(values)} for key, values in timing.items()},
        "answer_diagnostics": answers, "harness_errors": errors,
        "price": "unknown; no price schedule available for this provider's routing group"}


if __name__ == "__main__":
    assert not summarize([])["harness_errors"]
    sample = summarize([{"backend": "x", "step": "wire:completions", "elapsed_s": 1, "result": {
        "usage": {"prompt_tokens": 7, "completion_tokens": 2, "prompt_tokens_details": {"cached_tokens": 3}}}}])
    assert sample["reported_llm_usage"]["x"] == {"calls": 1, "prompt_tokens": 7, "completion_tokens": 2, "cached_prompt_tokens": 3}
    output = {}
    for arg in sys.argv[1:]:
        root = Path(arg)
        rows = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]
        output[root.name] = summarize(rows)
    print(json.dumps(output, ensure_ascii=False, indent=2))

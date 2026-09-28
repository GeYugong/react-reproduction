"""Rebuild compatibility evidence from the append-only request ledger."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def native_reasoning(response):
    messages = [c.get("message", {}) for c in response.get("choices", [])]
    details = (response.get("usage") or {}).get("completion_tokens_details") or {}
    return any(m.get("reasoning_content") or m.get("reasoning") for m in messages) or bool(details.get("reasoning_tokens"))


def main():
    rows = [json.loads(line) for line in (ROOT / "records/api_preflight.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    config = json.loads((ROOT / "configs/experiment.json").read_text(encoding="utf-8"))
    models = {}
    for row in rows:
        model = (row.get("request") or {}).get("model")
        if not model:
            continue
        models.setdefault(model, []).append(row)
    stats = {}
    for model, records in models.items():
        responses = [r.get("response") or {} for r in records]
        usage = [r.get("usage") or {} for r in responses]
        stats[model] = {
            "requests": len(records),
            "http_status_counts": dict(Counter(str(r["http_status"]) for r in records)),
            "native_reasoning_observed_responses": sum(bool(native_reasoning(r)) for r in responses),
            "missing_usage_responses": sum(not u for u in usage),
            "missing_reasoning_token_field_responses": sum("reasoning_tokens" not in (u.get("completion_tokens_details") or {}) for u in usage),
            "returned_models": sorted({r["model"] for r in responses if r.get("model")}),
            "known_prompt_tokens_sum": sum(u.get("prompt_tokens", 0) for u in usage),
            "known_completion_tokens_sum": sum(u.get("completion_tokens", 0) for u in usage),
            "reported_total_tokens_sum": sum(u.get("total_tokens", 0) for u in usage),
            "token_arithmetic_mismatches": sum(u.get("total_tokens") != u["prompt_tokens"] + u["completion_tokens"] for u in usage if all(k in u for k in ("total_tokens", "prompt_tokens", "completion_tokens"))),
        }
    selected = config["model"]["id"]
    # Latest result per fixed fixture; older failed probes remain in the ledger.
    fixtures = ["react_search", "react_finish", "act_format", "sampling_parameter", "stop_parameter"]
    checks = {}
    for fixture in fixtures:
        matches = [r for r in rows if r["label"] == fixture + "_" + selected]
        if not matches:
            checks[fixture] = {"passed": False, "reason": "not_run"}
            continue
        row = matches[-1]
        response = row["response"]
        content = (response.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        content = content.strip()
        valid = {
            "react_search": "Search[Amber Manual]" in content and "Thought 1:" in content and "Action 1:" in content,
            "react_finish": "Finish[K-17]" in content and "Action 2:" in content,
            "act_format": content == "Action 1: Finish[K-17]",
            "sampling_parameter": content in {"amber", "cobalt", "jade"},
            "stop_parameter": content == "alpha",
        }[fixture]
        checks[fixture] = {"passed": row["http_status"] == 200 and valid and not native_reasoning(response), "evidence_timestamp_utc": row["timestamp_utc"]}
    summary = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "api_requests": len(rows), "generation_requests": sum(len(r) for r in models.values()),
        "models": stats, "selected_main_model": selected,
        "selection_basis": "synthetic protocol compatibility, without benchmark scores",
        "protocol_checks": checks,
        "synthetic_protocol_passed": all(c["passed"] for c in checks.values()),
        "native_reasoning_disable_verified": False,
        "native_reasoning_evidence_scope": "enable_thinking=false; no extra reasoning observed in selected successful fixtures; missing telemetry is unknown, not zero",
        "upstream_mapping_verified": False,
        "actual_cost_cny": None, "cost_status": "pending_effective_gateway_rates_or_invoice",
        "monetary_cap_cny": None, "benchmark_episodes_run": 0,
    }
    (ROOT / "records/preflight_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"model": selected, "checks": checks, "api_requests": len(rows)}))


if __name__ == "__main__":
    main()

"""Record bounded API compatibility probes; never run benchmark episodes."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://aigw.saurlax.com"
ALLOWED_MODELS = {"qwen-3.8-27b", "qwen3.6-35b-a3b", "deepseek-v4-flash", "glm-5.3-flash", "glm-5.3", "step-3.7-flash", "step-5-preview", "grok-4.6"}
LOG = ROOT / "records" / "api_preflight.jsonl"
REASONING_EFFORT = None
STREAM = False


def scrub(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if any(s in key.lower() for s in ("api_key", "authorization", "cookie")) else scrub(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"sk-[A-Za-z0-9_-]{12,}", "[REDACTED]", value)
    return value


def request(label, path, payload=None):
    if payload is not None:
        if payload.get("model") not in ALLOWED_MODELS:
            raise ValueError("Model is outside the explicit non-GPT allowlist")
        if payload.get("max_tokens", 0) > 256 or payload.get("n", 1) != 1:
            raise ValueError("Probe output limit exceeded")
    key = os.environ["AIGW_API_KEY"]
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + path, data=body,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "User-Agent": "ReAct-Reproduction/0.1"},
    )
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    begin = time.monotonic()
    status, response, response_headers = None, None, {}
    try:
        with urllib.request.urlopen(req, timeout=45) as result:
            status = result.status
            raw = result.read().decode("utf-8", errors="replace")
            for name in ["Content-Type", "X-Request-ID", "X-Gateway-Cost", "X-Gateway-Billing-Currency"]:
                if result.headers.get(name):
                    response_headers[name] = result.headers[name]
    except urllib.error.HTTPError as error:
        status = error.code
        raw = error.read().decode("utf-8", errors="replace")
    except Exception as error:
        raw = json.dumps({"transport_error": type(error).__name__})
    try:
        response = json.loads(raw)
    except json.JSONDecodeError:
        if raw.startswith("data:") or "\ndata:" in raw:
            chunks = []
            for line in raw.splitlines():
                if line.startswith("data:") and line[5:].strip() != "[DONE]":
                    try:
                        chunks.append(json.loads(line[5:].strip()))
                    except json.JSONDecodeError:
                        pass
            content, reasoning, model, usage, finish = "", "", None, None, None
            for chunk in chunks:
                model = chunk.get("model") or model
                usage = chunk.get("usage") or usage
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta", {})
                    content += delta.get("content") or ""
                    reasoning += delta.get("reasoning_content") or delta.get("reasoning") or ""
                    finish = choice.get("finish_reason") or finish
            response = {"model": model, "usage": usage, "sse_chunks": chunks,
                        "choices": [{"message": {"content": content, "reasoning_content": reasoning}, "finish_reason": finish}]}
        else:
            response = {"non_json_response": raw[:2000]}
    record = scrub({
        "timestamp_utc": started,
        "phase": "plan_preflight",
        "label": label,
        "url": BASE_URL + path,
        "request": payload,
        "http_status": status,
        "elapsed_seconds": round(time.monotonic() - begin, 3),
        "response_headers": response_headers,
        "response": response,
        "actual_cost_cny": None,
        "cost_status": "not_reconciled",
        "benchmark_result": False,
    })
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    summary = {key: record[key] for key in ("label", "http_status", "elapsed_seconds")}
    if isinstance(response, dict):
        summary.update({key: scrub(response[key]) for key in ("model", "usage", "error") if key in response})
        if response.get("choices"):
            summary["choices"] = scrub(response["choices"])
        if path == "/v1/models":
            summary["models"] = scrub(response.get("data"))
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return record


def payload(model, messages, temperature=0, stop=None):
    result = {"model": model, "messages": messages, "temperature": temperature,
              "max_tokens": 128, "stream": STREAM}
    if STREAM:
        result["stream_options"] = {"include_usage": True}
    if model.startswith("qwen"):
        result["enable_thinking"] = False
    elif model.startswith(("deepseek", "glm", "step")):
        result["thinking"] = {"type": "disabled"}
    if stop:
        result["stop"] = stop
    if REASONING_EFFORT is not None:
        result["reasoning_effort"] = REASONING_EFFORT
    return result


def main():
    global REASONING_EFFORT, STREAM
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["metadata", "ping", "protocol"])
    parser.add_argument("--model", choices=sorted(ALLOWED_MODELS), default="qwen3.6-35b-a3b")
    parser.add_argument("--reasoning-effort", choices=["none", "low"])
    parser.add_argument("--stream", action="store_true")
    args = parser.parse_args()
    REASONING_EFFORT = args.reasoning_effort
    STREAM = args.stream
    if args.mode == "metadata":
        request("model_catalog", "/v1/models")
        request("pricing_access", "/api/model-marketplace")
    elif args.mode == "ping":
        request("ping_" + args.model, "/v1/chat/completions", payload(args.model, [
            {"role": "user", "content": "Reply with exactly: READY"}
        ]))
    else:
        messages = [{"role": "user", "content": (
            "Synthetic interface test. There is a fictional archive. Find the shelf of the Amber Manual. "
            "Allowed text actions: Search[title], Finish[shelf]. Output a short Thought 1 and Action 1. "
            "The program will provide Observation 1; do not invent it.\n"
            "Required format:\nThought 1: <short plan>\nAction 1: <action>"
        )}]
        first = request("react_search_" + args.model, "/v1/chat/completions",
                        payload(args.model, messages, stop=["\nObservation"]))
        if first["http_status"] != 200:
            return
        choice = first["response"].get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        if not content or "Search[" not in content:
            return
        messages += [{"role": "assistant", "content": content},
                     {"role": "user", "content": (
                         "Observation 1: The fictional Amber Manual is stored on shelf K-17.\n"
                         "Continue with Thought 2 and Action 2, then stop before Observation 2."
                     )}]
        request("react_finish_" + args.model, "/v1/chat/completions",
                payload(args.model, messages, stop=["\nObservation"]))
        request("act_format_" + args.model, "/v1/chat/completions", payload(args.model, [
            {"role": "user", "content": (
                "Synthetic archive task. Observation: The Amber Manual is on shelf K-17. "
                "Return only Action 1: Finish[K-17] without any Thought line."
            )}
        ], stop=["\nObservation"]))
        request("sampling_parameter_" + args.model, "/v1/chat/completions", payload(args.model, [
            {"role": "user", "content": "Return only one word from this list: amber, cobalt, jade."}
        ], temperature=0.7))
        request("stop_parameter_" + args.model, "/v1/chat/completions", payload(args.model, [
            {"role": "user", "content": "Copy this text exactly: alpha STOPMARK omega"}
        ], stop=[" STOPMARK"]))


if __name__ == "__main__":
    main()

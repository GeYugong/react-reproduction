"""Audited QA runner adapted from ReAct hotpotqa.ipynb / FEVER.ipynb.

Upstream: 6bdb3a1fd38b8188fc7ba4102969fe483df8fdc9 (MIT).
Preserves demonstration text, WikiEnv, scoring, and numbered interaction loop.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import SimpleNamespace
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from react_reproduction.author.wikienv import WikiEnv
from react_reproduction.author import wrappers


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def scrub(value):
    return re.sub(r"sk-[A-Za-z0-9_-]{12,}", "[REDACTED]", value)


class Journal:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, **record):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(scrub(json.dumps({"timestamp_utc": now(), **record}, ensure_ascii=False)) + "\n")
            f.flush()
            os.fsync(f.fileno())


class ProtocolError(RuntimeError):
    pass


class Client:
    def __init__(self, config, folder, journal):
        self.config, self.folder, self.journal = config, folder, journal
        self.key = os.environ["AIGW_API_KEY"]
        self.model = config["model"]["id"]
        if self.model != "qwen-3.8-27b":
            raise ProtocolError("Only the frozen Qwen model is permitted")

    def generate(self, prompt, method, call_id, stop=None):
        cfg = self.config["generation"]
        payload = {"model": self.model, "messages": [
            {"role": "system", "content": "Continue the provided text exactly from its final prefix. Do not repeat the prefix or earlier examples."},
            {"role": "user", "content": prompt}],
            "temperature": cfg["cot_sc_temperature"] if method == "cot_sc" else cfg["default_temperature"],
            "top_p": cfg["top_p"], "max_tokens": cfg["max_output_tokens"][method],
            **self.config["model"]["requested_controls"], "stream": False}
        if stop:
            payload["stop"] = stop
        cache_key = digest(json.dumps([call_id, payload], sort_keys=True).encode())
        path = self.folder / "responses" / (cache_key + ".json")
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.journal.add(event="api_cache_hit", call_id=call_id, cache_key=cache_key)
            return saved["content"]
        for attempt in range(cfg["max_transport_retries"] + 1):
            self.journal.add(event="api_dispatch", call_id=call_id, attempt=attempt, request=payload)
            started = time.monotonic()
            try:
                response = requests.post(self.config["model"]["base_url"] + "/chat/completions",
                    headers={"Authorization": "Bearer " + self.key, "User-Agent": "ReAct-Reproduction/0.1"},
                    json=payload, timeout=cfg["request_timeout_seconds"])
            except requests.RequestException as exc:
                self.journal.add(event="api_transport_error", call_id=call_id, attempt=attempt, error=type(exc).__name__, cost_status="unknown")
                if attempt == cfg["max_transport_retries"]:
                    raise
                time.sleep(2 ** attempt)
                continue
            try:
                body = response.json()
            except ValueError:
                body = {"non_json_response": response.text}
            self.journal.add(event="api_response", call_id=call_id, attempt=attempt, http_status=response.status_code,
                elapsed_seconds=time.monotonic()-started, response=body, cost_status="pending_reconciliation")
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < cfg["max_transport_retries"]:
                    time.sleep(2 ** attempt)
                    continue
            response.raise_for_status()
            if body.get("model") != self.model:
                raise ProtocolError("Response model differs from frozen alias")
            choice = body["choices"][0]
            message = choice["message"]
            details = (body.get("usage") or {}).get("completion_tokens_details") or {}
            if message.get("reasoning_content") or message.get("reasoning") or details.get("reasoning_tokens"):
                raise ProtocolError("Unexpected native reasoning; batch stopped")
            content = message.get("content") or ""
            if re.search(r"<think\b|<analysis\b", content, re.I):
                raise ProtocolError("Unexpected reasoning markup; batch stopped")
            write_json(path, {"content": content, "response": body, "request": payload, "call_id": call_id})
            return content
        raise RuntimeError("Exhausted API attempts")


class CachedWikipedia:
    def __init__(self, journal):
        self.journal = journal
        self.folder = ROOT / "data/cache/wikipedia-author-v1"
        self.folder.mkdir(parents=True, exist_ok=True)

    def __call__(self, url):
        path = self.folder / (digest(url.encode()) + ".json")
        hit = path.exists()
        if hit:
            saved = json.loads(path.read_text(encoding="utf-8"))
        else:
            response = requests.get(url, headers={"User-Agent": "ReAct-Reproduction/0.1"}, timeout=45)
            self.journal.add(event="wiki_http", url=url, status=response.status_code)
            response.raise_for_status()
            if "text/html" not in response.headers.get("Content-Type", ""):
                raise RuntimeError("Unexpected Wikipedia content type")
            saved = {"url": url, "resolved_url": response.url, "fetched_at_utc": now(), "text": response.text,
                     "sha256": digest(response.content)}
            write_json(path, saved)
        self.journal.add(event="wiki_page", url=url, cache_hit=hit, artifact=str(path.relative_to(ROOT)), sha256=saved["sha256"])
        return SimpleNamespace(text=saved["text"])


def parse_action(text, step, method):
    text = re.split(r"\nObservation(?:\s+\d+)?\s*:", text, maxsplit=1)[0].strip()
    match = re.search(r"(?:^|\n)Action\s+" + str(step) + r":\s*(Search|Lookup|Finish)\[(.*)\]\s*$", text, re.I)
    if not match and method == "act":
        match = re.fullmatch(r"(Search|Lookup|Finish)\[(.*)\]", text, re.I)
    if not match:
        return None
    if method == "act" and re.search(r"\bThought\s*\d*:", text, re.I):
        return None
    return match[1].lower() + "[" + match[2] + "]"


def final_answer(text, method):
    matches = re.findall(r"(?:^|\n)Answer:\s*(.*)", text, re.I)
    if matches:
        return matches[-1].strip()
    return text.strip().splitlines()[0] if method == "standard" and text.strip() else ""


def valid_answer(answer, dataset):
    norm = wrappers.normalize_answer(answer)
    return bool(norm) and (dataset != "fever" or norm in {"supports", "refutes", "not enough info"})


def vote(answers, dataset):
    valid = [(a, wrappers.normalize_answer(a)) for a in answers if valid_answer(a, dataset)]
    if not valid:
        return "", 0
    counts = Counter(n for a,n in valid)
    maximum = max(counts.values())
    return next(a for a,n in valid if counts[n] == maximum), maximum


def run_episode(client, env, prompt, dataset, method, index, limit, journal):
    question = env.reset(idx=index)
    context = prompt + question + "\n"
    trajectory = []
    answer, majority, termination = "", None, "step_limit"
    if method in {"standard", "cot", "cot_sc"}:
        answers = []
        count = 21 if method == "cot_sc" else 1
        for sample in range(count):
            prefix = "Answer:" if method == "standard" else "Thought:"
            output = client.generate(context + prefix, method, f"{dataset}/{index}/{method}/{sample}", ["\nQuestion:", "\nClaim:"])
            answer = final_answer(output, method)
            answers.append(answer)
            trajectory.append({"sample": sample, "output": output, "answer": answer})
        if method == "cot_sc":
            answer, majority = vote(answers, dataset)
        termination = "answer" if valid_answer(answer, dataset) else "invalid_answer"
        env.step("finish[" + answer + "]")
    else:
        for step in range(1, limit + 1):
            prefix = f"Thought {step}:" if method == "react" else f"Action {step}:"
            output = client.generate(context + prefix, method, f"{dataset}/{index}/{method}/{step}", [f"\nObservation {step}:"])
            # Chat APIs may either continue a prefix or repeat it; accept both fixed forms.
            rendered = output.strip() if output.lstrip().startswith((prefix, f"Action {step}:")) else prefix + output
            action = parse_action(rendered, step, method)
            observation, reward, done, info = env.step(action or "invalid_protocol_action")
            state = {k: getattr(env.unwrapped, k, None) for k in ("page", "lookup_keyword", "lookup_list", "lookup_cnt", "steps", "answer")}
            event = {"step": step, "output": output, "action": action, "observation": observation,
                     "done": done, "environment_state": state}
            trajectory.append(event)
            journal.add(event="environment_step", dataset=dataset, index=index, method=method, **event)
            # Model-created observations are never added to environment feedback.
            rendered = re.split(r"\nObservation(?:\s+\d+)?\s*:", rendered, maxsplit=1)[0]
            context += rendered + f"\nObservation {step}: " + observation.replace('\\n', '') + "\n"
            if done:
                answer = info.get("answer") or ""
                termination = "valid_finish" if valid_answer(answer, dataset) else "invalid_finish"
                break
    # Gold is accessed only after generation for scoring and reporting.
    gold = env.data[index][1]
    result = {"dataset": dataset, "index": index, "method": method, "model": client.model, "task": question,
              "trajectory": trajectory, "final_answer": answer, "ground_truth": gold,
              "correct": valid_answer(answer,dataset) and wrappers.normalize_answer(answer) == wrappers.normalize_answer(gold),
              "f1": wrappers.f1_score(answer,gold)[0] if dataset == "hotpotqa" else None,
              "majority_count": majority, "termination": termination, "completed_at_utc": now()}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["hotpotqa", "fever"], default="hotpotqa")
    parser.add_argument("--phase", choices=["pilot", "formal"], default="pilot")
    parser.add_argument("--methods", nargs="+", default=["react", "act", "standard", "cot"], choices=["react","act","standard","cot","cot_sc"])
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+",args.run_id):
        raise ValueError("Invalid run ID")
    config = json.loads((ROOT / "configs/experiment.json").read_text(encoding="utf-8"))
    if args.phase == "formal" and not config["formal_runs_enabled"]:
        raise RuntimeError("Formal runs are not enabled")
    manifest = json.loads((ROOT / "data/eval_manifest.json").read_text(encoding="utf-8"))["datasets"][args.dataset]
    source = ROOT / manifest["source_file"]
    assert digest(source.read_bytes()) == manifest["source_sha256"]
    indices = manifest["excluded_dev_smoke_rows"] if args.phase == "pilot" else [r["row_index"] for r in manifest["samples"]]
    if not 0 < args.limit <= len(indices):
        raise ValueError("Invalid sample limit")
    indices = indices[:args.limit]
    folder = ROOT / "runs/raw" / args.run_id
    folder.mkdir(parents=True, exist_ok=True)
    journal = Journal(folder / "events.jsonl")
    prompt_path = ROOT / "prompts" / ("prompts_naive.json" if args.dataset == "hotpotqa" else "fever.json")
    prompts = json.loads(prompt_path.read_text(encoding="utf-8"))
    fingerprint = {"config": config, "prompt_sha256": digest(prompt_path.read_bytes()), "dataset_sha256": manifest["source_sha256"], "indices": indices, "methods": args.methods, "phase": args.phase,
                   "runner_sha256": digest(Path(__file__).read_bytes()), "author_hashes": {n:digest((ROOT/'src/react_reproduction/author'/n).read_bytes()) for n in ['wikienv.py','wrappers.py']}}
    if (folder / "manifest.json").exists():
        prior = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if prior["fingerprint"] != fingerprint:
            raise RuntimeError("Run ID already belongs to a different experiment")
    else:
        write_json(folder / "manifest.json", {"started_at_utc": now(), "fingerprint": fingerprint,
                   "git_commit": subprocess.check_output(["git","rev-parse","HEAD"], cwd=ROOT,text=True).strip(),
                   "git_diff_sha256": digest(subprocess.check_output(["git","diff","HEAD"],cwd=ROOT)), "argv":sys.argv,
                   "python": sys.version})
        (folder/'run_qa.source.py').write_bytes(Path(__file__).read_bytes())
    client = Client(config, folder, journal)
    wrappers.DATA_DIR = str(ROOT / "vendor/ReAct/data")
    env = (wrappers.HotPotQAWrapper if args.dataset == "hotpotqa" else wrappers.FeverWrapper)(WikiEnv(CachedWikipedia(journal)),"dev")
    suffix = "6" if args.dataset == "hotpotqa" else "3"
    prefix = {"standard":"webqa_simple", "cot":"cotqa_simple", "cot_sc":"cotqa_simple", "act":"webact_simple", "react":"webthink_simple"}
    results = []
    try:
        for method in args.methods:
            for index in indices:
                path = folder / "episodes" / f"{args.dataset}-{index}-{method}.json"
                if path.exists():
                    result = json.loads(path.read_text(encoding="utf-8"))
                else:
                    journal.add(event="episode_start",dataset=args.dataset,index=index,method=method)
                    result = run_episode(client,env,prompts[prefix[method]+suffix],args.dataset,method,index,config["datasets"][args.dataset]["max_decisions"],journal)
                    write_json(path,result)
                results.append(result)
                progress = {"run_id":args.run_id,"phase":args.phase,"status":"running","completed":len(results),"planned":len(indices)*len(args.methods),"last":{"index":index,"method":method,"correct":result["correct"],"termination":result["termination"]},"updated_at_utc":now()}
                write_json(ROOT / "records" / (args.run_id + ".json"),progress)
                print(json.dumps(progress),flush=True)
        progress["status"] = "completed"
        progress["per_method"] = {m:{"n":sum(r['method']==m for r in results),"correct":sum(r['correct'] for r in results if r['method']==m)} for m in args.methods}
        write_json(ROOT / "records" / (args.run_id + ".json"),progress)
    except Exception as exc:
        journal.add(event="batch_stopped", error_type=type(exc).__name__, error=str(exc))
        write_json(ROOT / "records" / (args.run_id + ".json"),{"run_id":args.run_id,"status":"stopped","completed":len(results),"error_type":type(exc).__name__,"error":scrub(str(exc)),"updated_at_utc":now()})
        raise


if __name__ == "__main__":
    main()

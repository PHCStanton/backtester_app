"""
run_kb_loop.py - Autonomous orchestrator for AI Knowledge Base retrieval optimization.
Queries xAI Grok to optimize data structures/indexing in kb_retriever.py.
"""
import os
import sys
import json
import time
import subprocess
from pathlib import Path
import httpx

REPO_ROOT = Path(__file__).resolve().parents[3]
AUTORESEARCH_KB_DIR = Path(__file__).resolve().parent

# Load GROK_API_KEY from app/.env
ENV_PATH = REPO_ROOT / "app" / ".env"
GROK_API_KEY = ""

if ENV_PATH.exists():
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("GROK_API_KEY="):
                GROK_API_KEY = line.split("=", 1)[1].strip()
                if GROK_API_KEY.startswith(("'", '"')) and GROK_API_KEY.endswith(("'", '"')):
                    GROK_API_KEY = GROK_API_KEY[1:-1]
                break

if not GROK_API_KEY:
    print(f"Error: GROK_API_KEY not found in {ENV_PATH}")
    sys.exit(1)

# Model configuration
GROK_MODEL = os.getenv("GROK_MODEL", "grok-4.3")
XAI_API_URL = "https://api.x.ai/v1/chat/completions"

TARGET_FILE = AUTORESEARCH_KB_DIR / "kb_retriever.py"
HARNESS_FILE = AUTORESEARCH_KB_DIR / "kb_harness.py"
PROGRAM_FILE = AUTORESEARCH_KB_DIR / "kb_program.md"
RESULTS_FILE = AUTORESEARCH_KB_DIR / "results.tsv"

def read_file(path: Path) -> str:
    if not path.exists():
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write_file(path: Path, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def run_cmd(args: list[str], cwd: Path = REPO_ROOT) -> tuple[int, str]:
    try:
        res = subprocess.run(
            args,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            timeout=180
        )
        return res.returncode, res.stdout
    except Exception as e:
        return -2, f"Failed to execute command: {e}"

def query_grok(prompt: str, system_prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {GROK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": GROK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }
    
    print(f"Sending proposal request to xAI Grok ({GROK_MODEL})...")
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(XAI_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"xAI API Request failed: {e}")
        sys.exit(1)

def extract_python_code(llm_output: str) -> str:
    if "```python" in llm_output:
        parts = llm_output.split("```python", 1)[1]
        if "```" in parts:
            return parts.split("```", 1)[0].strip()
    elif "```" in llm_output:
        parts = llm_output.split("```", 1)[1]
        if "```" in parts:
            return parts.split("```", 1)[0].strip()
    return llm_output.strip()

def initialize_results_tsv():
    if not RESULTS_FILE.exists():
        write_file(RESULTS_FILE, "commit\tload_time_ms\tavg_query_time_ms\tfitness\tstatus\tdescription\n")

def log_result(commit: str, load_t: float, query_t: float, fitness: float, status: str, description: str):
    desc_clean = description.replace("\t", " ").replace("\n", " ").strip()
    with open(RESULTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{commit}\t{load_t:.4f}\t{query_t:.6f}\t{fitness:.4f}\t{status}\t{desc_clean}\n")

def get_git_head_hash() -> str:
    code, out = run_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=AUTORESEARCH_KB_DIR)
    return out.strip() if code == 0 else "0000000"

def get_recent_tsv_history(limit: int = 5) -> str:
    if not RESULTS_FILE.exists():
        return "No experiments recorded yet."
    lines = read_file(RESULTS_FILE).splitlines()
    if len(lines) <= 1:
        return "No experiments recorded yet."
    header = lines[0]
    recent = lines[-limit:]
    return "\n".join([header] + recent)

def run_loop():
    initialize_results_tsv()
    
    print("Establishing baseline performance...")
    harness_path = AUTORESEARCH_KB_DIR / "kb_harness.py"
    
    code, out = run_cmd(["conda", "run", "-n", "QuFLX-v2", "python", str(harness_path)], cwd=AUTORESEARCH_KB_DIR)
    write_file(AUTORESEARCH_KB_DIR / "run.log", out)
    
    metrics_path = AUTORESEARCH_KB_DIR / "metrics.json"
    if not metrics_path.exists():
        print("Error: Baseline run failed. Log output:")
        print(out)
        sys.exit(1)
        
    with open(metrics_path, "r") as f:
        metrics = json.load(f)
        
    best_fitness = float(metrics.get("fitness_score", 0.0))
    best_load_t = float(metrics.get("load_time_ms", 0.0))
    best_query_t = float(metrics.get("avg_query_time_ms", 0.0))
    
    print(f"Baseline established:")
    print(f"  Load Time    : {best_load_t:.4f} ms")
    print(f"  Query Time   : {best_query_t:.6f} ms")
    print(f"  Fitness Score: {best_fitness:.4f}")
    
    head_hash = get_git_head_hash()
    log_result(head_hash, best_load_t, best_query_t, best_fitness, "keep", "Baseline setup")
    
    system_prompt = """You are an expert software engineer and data structures researcher.
Your task is to autonomously modify kb_retriever.py to maximize the fitness score.

Fitness is computed as:
Fitness = 1000.0 / (avg_query_time_ms + 0.01 * load_time_ms + 0.001)

To achieve higher fitness:
1. Optimize indices and mapping lookups. E.g. replace list scanning with dictionary nested hash lookups, or precompute lookup structures during load().
2. Ensure you return valid matches (list of patterns matching clean_asset, regime, level similarity).
3. Do not change the function signature of load() or query().
4. Output only valid Python code inside a ```python ... ``` block.
"""

    iteration = 1
    while True:
        print(f"\n=========================================")
        print(f"KB Iteration {iteration} | Best Fitness: {best_fitness:.4f} (Avg Query: {best_query_t:.6f} ms)")
        print(f"=========================================")
        
        current_retriever = read_file(TARGET_FILE)
        instructions = read_file(PROGRAM_FILE)
        harness_code = read_file(HARNESS_FILE)
        history = get_recent_tsv_history()
        
        prompt = f"""### Instructions:
{instructions}

### Benchmark Harness Code:
```python
{harness_code}
```

### Recent Experiment Log:
```
{history}
```

### Current kb_retriever.py:
```python
{current_retriever}
```

Write a new, highly optimized version of kb_retriever.py to maximize the fitness score. Return the full code in a ```python ``` block.
"""
        llm_response = query_grok(prompt, system_prompt)
        new_code = extract_python_code(llm_response)
        
        description = "Optimized retrieval structures"
        lines = llm_response.splitlines()
        for line in lines:
            if line.lower().startswith("description:") or line.lower().startswith("summary:"):
                description = line.split(":", 1)[1].strip()
                break
                
        write_file(TARGET_FILE, new_code)
        
        run_cmd(["git", "add", "kb_retriever.py"], cwd=AUTORESEARCH_KB_DIR)
        commit_code, commit_out = run_cmd(["git", "commit", "-m", "autoresearch: temp kb commit"], cwd=AUTORESEARCH_KB_DIR)
        
        # Run benchmark
        print("Running benchmark...")
        run_code, run_out = run_cmd(["conda", "run", "-n", "QuFLX-v2", "python", str(harness_path)], cwd=AUTORESEARCH_KB_DIR)
        write_file(AUTORESEARCH_KB_DIR / "run.log", run_out)
        
        if metrics_path.exists():
            try:
                with open(metrics_path, "r") as f:
                    metrics = json.load(f)
                    
                valid = bool(metrics.get("valid_format", True))
                load_t = float(metrics.get("load_time_ms", 0.0))
                query_t = float(metrics.get("avg_query_time_ms", 0.0))
                fitness = float(metrics.get("fitness_score", 0.0))
                
                print(f"Results:")
                print(f"  Load Time    : {load_t:.4f} ms")
                print(f"  Query Time   : {query_t:.6f} ms")
                print(f"  Fitness Score: {fitness:.4f}")
                
                if valid and fitness > best_fitness:
                    best_fitness = fitness
                    best_load_t = load_t
                    best_query_t = query_t
                    
                    short_hash = get_git_head_hash()
                    commit_msg = f"autoresearch: improved KB fitness to {fitness:.4f} (Query: {query_t:.4f}ms) | {description}"
                    run_cmd(["git", "commit", "--amend", "-m", commit_msg], cwd=AUTORESEARCH_KB_DIR)
                    log_result(short_hash, load_t, query_t, fitness, "keep", description)
                    print(f"🏆 SUCCESS: KB Fitness improved to {fitness:.4f}! Commit kept: {short_hash}")
                else:
                    run_cmd(["git", "reset", "--hard", "HEAD~1"], cwd=AUTORESEARCH_KB_DIR)
                    log_result(get_git_head_hash(), load_t, query_t, fitness, "discard", description)
                    print(f"❌ DISCARD: KB Fitness ({fitness:.4f}) did not beat best ({best_fitness:.4f}). Changes reverted.")
            except Exception as e:
                print(f"Exception during parse: {e}")
                run_cmd(["git", "reset", "--hard", "HEAD~1"], cwd=AUTORESEARCH_KB_DIR)
                log_result(get_git_head_hash(), 0.0, 0.0, 0.0, "crash", f"Parsing exception: {e}")
        else:
            print("❌ CRASH: Benchmark harness failed.")
            run_cmd(["git", "reset", "--hard", "HEAD~1"], cwd=AUTORESEARCH_KB_DIR)
            log_result(get_git_head_hash(), 0.0, 0.0, 0.0, "crash", "Crashed during execution")
            
        iteration += 1
        time.sleep(2)

if __name__ == "__main__":
    try:
        run_loop()
    except KeyboardInterrupt:
        print("\nAutoresearch KB loop stopped by user.")

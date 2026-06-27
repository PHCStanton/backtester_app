"""
run_backtest_loop.py - Autonomous orchestrator for the strategy autoresearch loop.
Loads the xAI Grok API key, calls the LLM to propose code modifications to strategy_candidate.py,
runs the eval_harness.py, parses performance metrics, and uses Git to commit/revert.
"""
import os
import sys
import json
import time
import shutil
import subprocess
from pathlib import Path
import httpx

# Ensure project root is in path
REPO_ROOT = Path(__file__).resolve().parents[2]
AUTORESEARCH_DIR = Path(__file__).resolve().parent

# Load GROK_API_KEY from app/.env
ENV_PATH = REPO_ROOT / "app" / ".env"
GROK_API_KEY = ""

if ENV_PATH.exists():
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("GROK_API_KEY="):
                GROK_API_KEY = line.split("=", 1)[1].strip()
                # Strip quotes if present
                if GROK_API_KEY.startswith(("'", '"')) and GROK_API_KEY.endswith(("'", '"')):
                    GROK_API_KEY = GROK_API_KEY[1:-1]
                break

if not GROK_API_KEY:
    print(f"Error: GROK_API_KEY not found in {ENV_PATH}")
    print("Please configure your xAI API key in the app/.env file first.")
    sys.exit(1)

# Model configuration
GROK_MODEL = os.getenv("GROK_MODEL", "grok-4.3")
XAI_API_URL = "https://api.x.ai/v1/chat/completions"


# File targets
TARGET_FILE = AUTORESEARCH_DIR / "strategy_candidate.py"
HARNESS_FILE = AUTORESEARCH_DIR / "eval_harness.py"
PROGRAM_FILE = AUTORESEARCH_DIR / "program.md"
RESULTS_FILE = AUTORESEARCH_DIR / "results.tsv"

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
            timeout=300 # 5-minute timeout per command
        )
        return res.returncode, res.stdout
    except subprocess.TimeoutExpired as e:
        return -1, f"Command timed out: {e.output}"
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
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response text: {e.response.text}")
        sys.exit(1)

def extract_python_code(llm_output: str) -> str:
    # Look for code block markers
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
        write_file(RESULTS_FILE, "commit\twin_rate\ttotal_trades\tstatus\tdescription\n")
        print(f"Initialized {RESULTS_FILE.name}")

def log_result(commit: str, win_rate: float, trades: int, status: str, description: str):
    # Tab-separated formatting to prevent parsing breaks
    desc_clean = description.replace("\t", " ").replace("\n", " ").strip()
    with open(RESULTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{commit}\t{win_rate:.4f}\t{trades}\t{status}\t{desc_clean}\n")

def get_git_head_hash() -> str:
    code, out = run_cmd(["git", "rev-parse", "--short", "HEAD"], cwd=AUTORESEARCH_DIR)
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
    
    # Establish baseline fitness
    print("Establishing baseline performance...")
    harness_path = AUTORESEARCH_DIR / "eval_harness.py"
    
    # Run the harness in the conda environment
    code, out = run_cmd(["conda", "run", "-n", "QuFLX-v2", "python", str(harness_path)], cwd=AUTORESEARCH_DIR)
    write_file(AUTORESEARCH_DIR / "run.log", out)
    
    metrics_path = AUTORESEARCH_DIR / "metrics.json"
    if not metrics_path.exists():
        print("Error: Baseline run failed to produce metrics.json. Log output:")
        print(out)
        sys.exit(1)
        
    with open(metrics_path, "r") as f:
        metrics = json.load(f)
        
    best_fitness = float(metrics.get("fitness_score", 0.0))
    best_win_rate = float(metrics.get("win_rate", 0.0))
    best_trades = int(metrics.get("total_trades", 0))
    
    print(f"Baseline established:")
    print(f"  Win Rate     : {best_win_rate:.4f}%")
    print(f"  Total Trades : {best_trades}")
    print(f"  Fitness Score: {best_fitness:.4f}")
    
    # Log baseline to TSV if not already present
    head_hash = get_git_head_hash()
    log_result(head_hash, best_win_rate, best_trades, "keep", "Baseline setup")
    
    system_prompt = f"""You are an expert algorithmic quantitative researcher.
Your task is to autonomously iterate on the strategy_candidate.py file to improve the fitness score.

The objective is simple: maximize the fitness score.
Fitness Score = Win Rate * ln(Total Trades)
Vetoes and exipry durations are under your control.
Conditions to meet:
1. Trade count must be at least 30, and win rate must be >= 52.08% to get a non-zero fitness score.
2. Keep edits simple and robust. Prefer simple math formulas over over-complex or convoluted rules.
3. Only output valid Python code enclosed in a ```python ... ``` block. Do not include extra conversational text outside the code block.
"""

    iteration = 1
    while True:
        print(f"\n=========================================")
        print(f"Iteration {iteration} | Best Fitness: {best_fitness:.4f} (WR: {best_win_rate:.2f}%)")
        print(f"=========================================")
        
        # Gather context files
        current_strategy = read_file(TARGET_FILE)
        instructions = read_file(PROGRAM_FILE)
        harness_code = read_file(HARNESS_FILE)
        history = get_recent_tsv_history()
        
        prompt = f"""### Instructions & Guidelines:
{instructions}

### Evaluation Harness Code (Immutable):
```python
{harness_code}
```

### Recent Experiment Log History:
```
{history}
```

### Current strategy_candidate.py:
```python
{current_strategy}
```

### Goal:
Write a new version of strategy_candidate.py that improves the fitness score.
You can adjust:
- Expiry duration calculations (e.g. use volatility or ATR to dynamically scale expiry).
- Veto bounds for Hurst parameters or ADX values.
- Conditional entry rules based on active regime labels (e.g., allow certain trends, restrict CHOPS).

Propose a creative, mathematically grounded optimization. Provide the full code of the updated strategy_candidate.py inside a ```python ``` block.
"""
        # Call Grok
        llm_response = query_grok(prompt, system_prompt)
        new_code = extract_python_code(llm_response)
        
        # Extract explanation/description from LLM response (rough parsing)
        description = "Optimized strategy"
        lines = llm_response.splitlines()
        for line in lines:
            if line.lower().startswith("description:") or line.lower().startswith("summary:"):
                description = line.split(":", 1)[1].strip()
                break
        
        # Write to strategy candidate
        write_file(TARGET_FILE, new_code)
        
        # Stage and commit locally before run
        run_cmd(["git", "add", "strategy_candidate.py"], cwd=AUTORESEARCH_DIR)
        commit_code, commit_out = run_cmd(["git", "commit", "-m", "autoresearch: temp commit"], cwd=AUTORESEARCH_DIR)
        
        # Run experiment
        print("Running candidate evaluation...")
        run_code, run_out = run_cmd(["conda", "run", "-n", "QuFLX-v2", "python", str(harness_path)], cwd=AUTORESEARCH_DIR)
        write_file(AUTORESEARCH_DIR / "run.log", run_out)
        
        # Parse metrics
        if metrics_path.exists():
            try:
                with open(metrics_path, "r") as f:
                    metrics = json.load(f)
                
                win_rate = float(metrics.get("win_rate", 0.0))
                total_trades = int(metrics.get("total_trades", 0))
                fitness = float(metrics.get("fitness_score", 0.0))
                
                print(f"Results:")
                print(f"  Win Rate     : {win_rate:.4f}%")
                print(f"  Total Trades : {total_trades}")
                print(f"  Fitness Score: {fitness:.4f}")
                
                # Check for improvement
                if fitness > best_fitness:
                    best_fitness = fitness
                    best_win_rate = win_rate
                    best_trades = total_trades
                    
                    # Amend commit with details
                    short_hash = get_git_head_hash()
                    commit_msg = f"autoresearch: improved fitness to {fitness:.4f} (WR: {win_rate:.2f}%, Trades: {total_trades}) | {description}"
                    run_cmd(["git", "commit", "--amend", "-m", commit_msg], cwd=AUTORESEARCH_DIR)
                    log_result(short_hash, win_rate, total_trades, "keep", description)
                    print(f"🏆 SUCCESS: Fitness improved to {fitness:.4f}! Commit kept: {short_hash}")
                else:
                    # Revert commit and file
                    run_cmd(["git", "reset", "--hard", "HEAD~1"], cwd=AUTORESEARCH_DIR)
                    log_result(get_git_head_hash(), win_rate, total_trades, "discard", description)
                    print(f"❌ DISCARD: Fitness ({fitness:.4f}) did not beat best ({best_fitness:.4f}). Changes reverted.")
            except Exception as e:
                # Revert on metric parsing exception
                print(f"Exception during metric parse: {e}")
                run_cmd(["git", "reset", "--hard", "HEAD~1"], cwd=AUTORESEARCH_DIR)
                log_result(get_git_head_hash(), 0.0, 0, "crash", f"Metric parsing exception: {e}")
        else:
            # Crash
            print("❌ CRASH: Evaluation harness failed to produce metrics.json.")
            # Revert commit and file
            run_cmd(["git", "reset", "--hard", "HEAD~1"], cwd=AUTORESEARCH_DIR)
            log_result(get_git_head_hash(), 0.0, 0, "crash", "Syntax or runtime execution crash")
            
        iteration += 1
        time.sleep(2)

if __name__ == "__main__":
    try:
        run_loop()
    except KeyboardInterrupt:
        print("\nAutoresearch loop stopped by user.")

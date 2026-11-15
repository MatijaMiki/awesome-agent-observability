# τ²-bench (new entry)

Checked 2026-11-15 on the already-installed clone at `sierra-research/tau2-bench` `c06b07d` (main), with the project's `.venv`. MIT. Created 2025-06-09.

Claim in the list line: simulates a tool-using agent and a user through customer-service tasks and scores each trial by the gold database end state and required communicated information.

Auth: no provider API keys. Agent and user were both `ollama/qwen2.5:3b-instruct` through LiteLLM (`api_base: http://127.0.0.1:11434`). The communicate-info scorer was `substring` so the optional semantic judge did not need a hosted model.

```
tau2 check-data
# Data directory: .../tau2-bench/data
# ✅ Data directory exists

tau2 run --domain mock --benchmark none \
  --agent-llm ollama/qwen2.5:3b-instruct \
  --user-llm ollama/qwen2.5:3b-instruct \
  --agent-llm-args '{"api_base":"http://127.0.0.1:11434","temperature":0.0}' \
  --user-llm-args '{"api_base":"http://127.0.0.1:11434","temperature":0.0}' \
  --communicate-scorer substring \
  --task-ids create_task_1 --num-trials 1 --max-steps 8 --timeout 180 \
  --save-to aao-gaps-mock
```

Result: one half-duplex simulation of `create_task_1`, 63.29 s, terminated at `max_steps`, reward **0.000** (Pass^1 0.000). The note was "Simulation terminated prematurely. Termination reason: max_steps". The 3B model did not finish the task, which was expected; the run shows that the orchestrator, user simulator, tools, and scorer all ran and wrote `results.json`.

A previous pass (#41) had installed τ²-bench but did not run it, so it failed threshold 8 at that time.

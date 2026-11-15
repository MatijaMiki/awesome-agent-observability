# BFCL (new entry)

Checked 2026-11-15 with PyPI `bfcl-eval==2026.3.23` (byte-identical to `ShishirPatil/gorilla` default-branch commit `6ea5797` on 2026-03-23, the Berkeley Function Calling Leaderboard tree). Apache-2.0. The gorilla repository was created 2023-05-19. The last default-branch commit is within 12 months (about 237 days before this check; the 9-month watch mark is around 2026-12-18).

Claim in the list line: evaluates a model's function calling on single-turn, live, multi-turn, and agentic web-search and memory tasks, checking single-turn calls by AST match and running multi-turn and agentic calls against the benchmark's API backends.

The CLI needed an extra `soundfile` package before it would start (`qwen_agent` imports it at import time). After that:

```
bfcl test-categories   # includes simple_python, multi_turn_*, memory_*, web_search_*, format_sensitivity
bfcl evaluate --model Qwen/Qwen3-0.6B --test-category simple_python --partial-eval \
  --result-dir result --score-dir score
```

The result file was a two-item fixture, not a live generation (OSS generate handlers expect a vLLM/SGLang server or a Hugging Face model id/tokenizer, not a bare Ollama name; no provider keys were used):

- `simple_python_0`: `[calculate_triangle_area(base=10, height=5)]` (gold)
- `simple_python_1`: `[wrong_function(x=1)]` (wrong name; gold is `math.factorial(number=5)`)

`bfcl evaluate` reported **accuracy 50.00% (1/2)**. The miss was tagged `simple_function_checker:wrong_func_name` / "Function name 'math.factorial' not found in model output.", with the decoded call `{"wrong_function": {"x": 1}}`. Leaderboard CSVs for the non-live, live, multi-turn, and agentic sections were written.

This exercises the deterministic grader. Live `bfcl generate` against Ollama was not run.

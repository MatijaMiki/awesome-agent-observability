# ctxlens (new entry)

Checked 2026-11-15 with `AgentPostmortem/Ctxlens` installed from the clone into a local venv (`ctxlens-cli` 0.1.1, MIT). Created 2026-07-27 (older than 8 weeks). Last default-branch commit 2026-10-01.

Claim in the list line: parses coding-agent transcripts and reports context composition, a waste ratio, and recommendations.

Input: a real Claude Code session from this box (`0745caec-…jsonl`, 37 lines, a coder-eval run on `qwen3.5:4b-fast`).

```
ctxlens analyze <session.jsonl>
ctxlens analyze <session.jsonl> --json
```

Human and JSON output agreed: format `claude-code-jsonl`, tokenizer `tiktoken:cl100k_base`, **2,894 tokens**, 4 turns, waste **33 tokens (1.1%)**, all of it duplicate tokens (the working-directory line appeared twice). A `[MEDIUM] Repeated content wastes tokens` recommendation was issued. Tool-result bloat, stale outputs, and oversized tool defs were 0 on this short session.

`pytest` in the project's `tests/` directory: **71 passed**.

The same session was also run through Tokenauditor 0.3.1 and agentxray 0.3.0 for comparison (see the PR body); they are not added.

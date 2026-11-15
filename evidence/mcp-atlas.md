# MCP-Atlas (new entry)

Checked 2026-11-15 with `scaleapi/mcp-atlas` at the shallow tip of `main` (image `ghcr.io/scaleapi/mcp-atlas:1.2.7`). MIT. Created 2025-12-01. Last default-branch commit 2026-10-29.

Claim in the list line: runs an agent against real MCP servers in a Docker sandbox and scores answers with claim-level judging.

Auth: no provider API keys. The harness was pointed at Ollama's OpenAI-compatible endpoint (`LLM_BASE_URL=http://127.0.0.1:11434`, dummy `LLM_API_KEY`). The sandbox and harness were bound to 127.0.0.1. Both were stopped after the run.

`GET /enabled-servers` after startup: 20 default no-key servers, **13 online / 7 offline**. Offline servers included `ddg-search` and `cli-mcp-server`, which failed inside the image with a FastMCP/MCP 2.x import error. `filesystem` was online.

The official smoke task ("first word of `/data/Barber Shop.csv`", expected "Customer"):

- `qwen2.5:3b-instruct` answered `25562.json` without a tool call (the model is too weak; the harness still loaded the live `filesystem_read_text_file` schema and completed the loop).
- `qwen3.5:4b-fast`, asked to call the tool, called `filesystem_read_text_file` with `path="/data/Barber Shop.csv", head=1`. The server returned the header line `Customer Gender,Customer Age,...`. The agent answered: `The first word of the file is "Customer".`

Claim-coverage scoring (`score_claims.py`) was not run in this pass; it needs a ground-truth claims file and a judge model. The smoke test exercises the sandbox, the real MCP tool, and the agent loop, which is the behaviour in the list line.

Processes stopped: the TypeScript harness on 127.0.0.1:3001 and the `mcp-atlas-sandbox` container on 127.0.0.1:1984.

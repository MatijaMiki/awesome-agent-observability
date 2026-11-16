# PurpleLlama (new entry)

Checked 2026-11-16. Repository `meta-llama/PurpleLlama`: created 2023-12-06 (older than 8 weeks), last default-branch commit 2026-11-13, not archived. GitHub reports the license as NOASSERTION because the repository mixes licenses: the README's license table, and the `LICENSE` files in `CodeShield/`, `CybersecurityBenchmarks/`, and `LlamaFirewall/`, say MIT for code and benchmarks; the Llama Guard and Prompt Guard models use Llama 2, 3, or 3.2 community licenses.

Installed from PyPI in a local venv (Python 3.13): `codeshield` 1.0.1 and `llamafirewall` 1.0.3.

Run:

```python
r = await CodeShield.scan_code('import hashlib\ndef h(p):\n    return hashlib.md5(p.encode()).hexdigest()\n')
fw = LlamaFirewall(scanners={Role.ASSISTANT: [ScannerType.CODE_SHIELD], Role.USER: [ScannerType.HIDDEN_ASCII, ScannerType.REGEX]})
fw.scan(AssistantMessage(content=<the MD5 code above>))
fw.scan(UserMessage(content="What is the weather in NYC?"))
fw.scan(UserMessage(content="my key is AKIAIOSFODNN7EXAMPLE and email bob@example.com"))
```

Output:

```
CODESHIELD insecure is_insecure= True action= Treatment.WARN [('CWE-327', 'weak-md5-hashing'), ('CWE-327', 'risky-crypto-algorithm'), ('CWE-328', 'insecure-md5-hash-usage')]
CODESHIELD safe is_insecure= False action= Treatment.IGNORE []
FW assistant insecure: ScanResult(decision=BLOCK, reason='3 unsafe function call detected: ...', score=1.0)
FW user benign: ScanResult(decision=ALLOW, reason='HIDDEN_ASCII: No hidden ASCII detected; REGEX: No regex patterns matched', score=0.0)
FW user secret: ScanResult(decision=BLOCK, reason='REGEX: Regex match: Email address', score=1.0)
```

`ScanDecision` in 1.0.3 has `ALLOW`, `BLOCK`, and `HUMAN_IN_THE_LOOP_REQUIRED`; `ScannerType` has `CODE_SHIELD`, `PROMPT_GUARD`, `AGENT_ALIGNMENT`, `HIDDEN_ASCII`, `PII_DETECTION`, and `REGEX`.

Not run:

- Prompt Guard and the Llama Guard models. The Hugging Face weights are gated, and on this box both `ollama pull llama-guard3:1b` and a Hugging Face GGUF pull failed at the download redirect (network policy). The models are described from the repository README.
- The alignment-check scanner, which calls a hosted model by default.
- CyberSecEval, described from `CybersecurityBenchmarks/README.md`.

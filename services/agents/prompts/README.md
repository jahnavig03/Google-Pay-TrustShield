# Prompts

Versioned prompt templates. File name = `<name>.<version>.md`. The active version of each prompt
is set in `config/prompts.yaml`. Never edit a released version in place: copy it to `v2`, switch
the config, and re-run `evals/run_evals.py` to compare.

| Prompt | Used by | Model env var |
| --- | --- | --- |
| `scam_context` | Scam Context agent (gcp mode) | `GEMINI_FAST_MODEL` |
| `customer_message` | Orchestrator fusion step (gcp mode, non-ALLOW decisions) | `GEMINI_FAST_MODEL` |

Placeholders use `{name}` and are filled with `str.format`.

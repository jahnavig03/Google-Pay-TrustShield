# evals/ — eval sets + runner (owner: Jahnavi)

| File | What |
| --- | --- |
| `scam_messages.jsonl` | 40 synthetic scam messages (6 patterns, English + Hinglish) + 10 legitimate-but-urgent hard negatives |
| `payment_scenarios.jsonl` | 30 payments (12 high-risk, 10 hard negatives, 8 normal) with their own features and an expected decision band |
| `tone_checks.py` | Flags accusatory / alarming wording, any PIN/OTP/password/CVV/card-number mention, missing safe actions |
| `run_evals.py` | Runs both sets through `evaluate_payment`, writes `results/<date>.md` against PRD §2 targets |

```bash
cd services/agents && source .venv/bin/activate
python ../../evals/run_evals.py              # mock mode
python ../../evals/run_evals.py --mode gcp   # real Gemini (needs GCP env + ADC)
```

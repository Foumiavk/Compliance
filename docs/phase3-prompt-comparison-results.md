# Prompt strategy comparison (live mode)

| Strategy | Runs | All-checks pass | Citation presence | Section format | Avg latency (s) | Tokens | Model calls |
|---|---|---|---|---|---|---|---|
| minimal | 24 | 17% | 17% | 0% | 8.1 | 109238 | 57 |
| guardrailed | 24 | 79% | 79% | 0% | 12.306 | 200409 | 79 |
| structured | 24 | 96% | 96% | 100% | 9.926 | 191119 | 75 |
| few_shot | 24 | 100% | 100% | 100% | 10.107 | 191149 | 75 |

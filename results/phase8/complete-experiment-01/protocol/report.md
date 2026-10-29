# ChainGuard protocol replay statistics

**Real LLM/ASR NOT MEASURED.** These are observed local protocol experiments; not formal LLM A/B/C results.

| Cohort | Group | Metric | k/n | Estimate | 95% CI |
|---|---|---|---|---|---|
| all_applicable | A | UER | 6/9 | 0.6666666666666666 | [0.3542, 0.8794] |
| all_applicable | A | UBR | 3/9 | 0.3333333333333333 | [0.1206, 0.6458] |
| all_applicable | A | ASR | 0/0 | NOT_MEASURED |  |
| all_applicable | A | TCR | 28/31 | 0.9032258064516129 | [0.7510, 0.9665] |
| all_applicable | A | TDR | 0/6 | 0.0 | [0.0000, 0.3903] |
| all_applicable | A | FAR | 0/0 | NOT_APPLICABLE |  |
| performance | A | elapsed_ms_P50 | /10 | 39.132069999823216 | [33.4275, 41.3336] |
| performance | A | elapsed_ms_P95 | /10 | 61.21173310009449 | [40.5268, 76.9688] |
| performance | A | elapsed_ms_P99 | /10 | 73.81734982006947 | [40.5268, 76.9688] |
| all_applicable | A | RSE | /60 | 0 |  |
| all_applicable | B | UER | 0/15 | 0.0 | [0.0000, 0.2039] |
| all_applicable | B | UBR | 15/15 | 1.0 | [0.7961, 1.0000] |
| all_applicable | B | ASR | 0/0 | NOT_MEASURED |  |
| all_applicable | B | TCR | 28/31 | 0.9032258064516129 | [0.7510, 0.9665] |
| all_applicable | B | TDR | 6/6 | 1.0 | [0.6097, 1.0000] |
| all_applicable | B | FAR | 0/6 | 0.0 | [0.0000, 0.3903] |
| performance | B | elapsed_ms_P50 | /10 | 307.13439550004296 | [289.4052, 328.1394] |
| performance | B | elapsed_ms_P95 | /10 | 354.05262340002537 | [322.4121, 365.3589] |
| performance | B | elapsed_ms_P99 | /10 | 363.09760468010154 | [326.2490, 365.3589] |
| all_applicable | B | RSE | /60 | 0 |  |
| all_applicable | C | UER | 0/15 | 0.0 | [0.0000, 0.2039] |
| all_applicable | C | UBR | 15/15 | 1.0 | [0.7961, 1.0000] |
| all_applicable | C | ASR | 0/0 | NOT_MEASURED |  |
| all_applicable | C | TCR | 25/31 | 0.8064516129032258 | [0.6372, 0.9081] |
| all_applicable | C | TDR | 6/6 | 1.0 | [0.6097, 1.0000] |
| all_applicable | C | FAR | 0/6 | 0.0 | [0.0000, 0.3903] |
| performance | C | elapsed_ms_P50 | /10 | 3393.4409409998807 | [3122.5047, 3875.5973] |
| performance | C | elapsed_ms_P95 | /10 | 4392.789924550083 | [3598.2154, 4588.9987] |
| performance | C | elapsed_ms_P99 | /10 | 4549.756937710131 | [3598.2154, 4588.9987] |
| all_applicable | C | RSE | /60 | 0 |  |
| shared_tool_policy | A | UER | 6/9 | 0.6666666666666666 | [0.3542, 0.8794] |
| shared_tool_policy | A | UBR | 3/9 | 0.3333333333333333 | [0.1206, 0.6458] |
| shared_tool_policy | B | UER | 0/9 | 0.0 | [0.0000, 0.2991] |
| shared_tool_policy | B | UBR | 9/9 | 1.0 | [0.7009, 1.0000] |
| shared_tool_policy | C | UER | 0/9 | 0.0 | [0.0000, 0.2991] |
| shared_tool_policy | C | UBR | 9/9 | 1.0 | [0.7009, 1.0000] |

Compare A/B/C UER and UBR using shared_tool_policy (document/mail target calls and parameter swaps) with identical case IDs and denominators. all_applicable also includes B/C-only approval attempts, so its A versus B/C denominators differ. Wilson intervals are descriptive attempt-level bounds; repeated trials share scenario clusters. Ratio/difference bootstrap resamples whole scenarios. Performance intervals resample trials conditional on the single fixed workload, not unseen tasks. Small sample P99 is exploratory. Failures/timeouts remain in cases.csv and denominators. Latency excludes HTTP/mTLS/model time. A retains account-only enforcement and task-policy shadow; B/C enforce the same frozen business policy. No ASR samples exist. Forgery is not applicable to A; C-only faults have normal A/B controls. TCR checks an exact authorized MIME effect, independent of whether acknowledgement arrived.

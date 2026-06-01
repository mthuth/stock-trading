# Score Driver Glossary

This glossary explains score driver and daily decision-review language in plain English.

It is explanatory and review-only. It does not change scoring formulas, weights, thresholds, targets, decision gates, allocation, broker behavior, or recommendations. It does not place trades, preview orders, write to broker accounts, or imply guaranteed performance.

| Term | Plain-English meaning |
| --- | --- |
| Base evidence | What the core facts say before trend movement, target confidence, data gaps, or final action checks are layered on. |
| Trend | Whether the market is confirming or fighting the thesis right now through price, momentum, score movement, or related confirmation signals. |
| Target | The upside estimate and the target evidence behind it, including analyst, fundamental, technical, manual, or blended target context. |
| Gap | What the app does not know well enough yet because data is missing, stale, blocked, or low-quality. |
| Final action | The controlled recommendation label shown after score, target, decision-safety, watchlist, allocation, and data-readiness checks. |
| Score driver | A factor that explains why the model likes, dislikes, or is cautious about an idea. |
| Score risk | A factor that could make the score less trustworthy or the setup less attractive. |
| Target confidence | How much trust to put in the displayed upside estimate based on source breadth, freshness, corroboration, price availability, and unresolved gaps. |
| Data status | Whether the inputs behind the target or recommendation context are fresh enough for the review question. |
| Decision gate | The safety checkpoint before treating an idea as ready for manual action. |
| Source health | Whether the research and data sources feeding the view are working, current, and reliable. |
| Provider gap | A provider-specific missing, blocked, stale, rate-limited, or expected data issue that should be visible instead of silently ignored. |
| Allocation cap | How much room the portfolio has before a position or sleeve gets too large. |
| Watchlist-only | Interesting enough to track, not ready enough to buy/add until evidence, confidence, and guardrails improve. |
| Model/user disagreement | A review-only learning signal when Matt and the model disagree; it is not permission to change the model automatically. |
| Review-only output | Decision support for Matt, not execution, automatic tuning, broker writes, order preview, or guaranteed performance. |

## Score Component Mapping

| Score component | Glossary entry |
| --- | --- |
| `base`, `base_evidence`, `base_score`, `evidence` | Base evidence |
| `trend`, `trends`, `trend_delta`, `momentum` | Trend |
| `target`, `targets`, `target_delta`, `blended_target` | Target |
| `gap`, `gaps`, `data_gap`, `data_gaps`, `data_gap_delta` | Gap |
| `final`, `final_action`, `action` | Final action |
| `score_driver`, `driver`, `drivers` | Score driver |
| `score_risk`, `risk`, `risks` | Score risk |
| `target_confidence`, `confidence` | Target confidence |
| `data_status` | Data status |
| `decision_gate`, `gate` | Decision gate |
| `source_health` | Source health |
| `provider_gap` | Provider gap |
| `allocation_cap` | Allocation cap |
| `watchlist_only`, `watchlist` | Watchlist-only |
| `model_user_disagreement` | Model/user disagreement |
| `review_only` | Review-only output |

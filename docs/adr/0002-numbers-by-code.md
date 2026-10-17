# ADR 0002: Deterministic Statistics and Two-Layer Fact-Checker

## Status
Accepted

## Context
Large language models are inherently probabilistic and prone to hallucinating numbers, inventing historical statistics, or confusing actors during complex match events. In live sports commentary, presenting fabricated statistics destroys credibility.

Earlier prototype iterations revealed that asking models to both calculate statistics and draft commentary simultaneously led to frequent discrepancies between simulated match events and spoken claims.

## Decision
1. **Deterministic Code Owns Every Statistic:**
   - The match ledger (`Ledger`, `app/ledger/`) ingests raw simulation events and computes all domain metrics deterministically (e.g., pass streaks, possession percentages, pressure counts, shot totals).
   - Models are forbidden from calculating or inventing match statistics. Agents must cite specific evidence keys (e.g., `pass_count`, `home_possession_pct`) provided in the candidate moment evidence dictionary.

2. **Two-Layer Fact-Checker Gate:**
   - Every candidate insight and narrative passes through the Fact-Checker (`app/agents/fact_checker.py`, `app/agents/fact_check_rules.py`) before publication.
   - **Layer 1 (Deterministic Code Rules):**
     - Extracts all numbers from candidate text across English and Turkish formats.
     - Matches numbers against cited evidence values using half-up rounding to the text precision and unit/family compatibility rules.
     - Enforces strict actor attribution: the moment belongs to the acting team (`labels['team']`). The opponent and opponent players may only appear in passive or recipient positions (e.g., "against Ironvale", "pinned by Kestrel Bay").
   - **Layer 2 (Model Wording Judge):**
     - Only runs if Layer 1 passes. An evaluation model assesses whether the narrative wording faithfully captures the underlying insight without misleading extrapolation.

3. **Retry and Fallback:**
   - If an insight fails verification, the Commentator receives the rejection reasons as feedback and is allowed one retry attempt.
   - If verification fails again, the moment is discarded or replaced with a safe fallback template.

## Consequences
- **Positive:**
  - Zero hallucinated numbers or mistaken actor attributions reach broadcast or voice output.
  - Sub-millisecond rejection of invalid statistics at Layer 1 saves model tokens and API latency.
  - Full auditability: every number on screen maps directly to an ingested simulation event in the ledger.
- **Negative / Trade-offs:**
  - Strict phrasing constraints require careful prompt engineering and grammar checking to avoid false-positive rejections.
  - Adding new statistical metrics requires explicit ledger definitions and family mapping in rule tables.

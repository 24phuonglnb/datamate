# Engineering Roadmap — DataMate V3+

> Priorities are ordered by expected accuracy gain vs. implementation cost.
> All proposals are hypotheses derived from root-cause analysis of the 31 V2 failures.
> Each must be verified against the synthetic benchmark before being claimed as a fix.

---

## Priority 1 — Low-effort, high-confidence fixes

### 1.1 String/date type normalisation (5 free points)

**Root cause:** The model returns `type: "date"` for YYYY-MM-DD results, but five ground-truth entries are typed `string`. The *values* are correct; only the type label mismatches.

**Hypothesis:** Normalise `date` → `string` in the evaluator (or in the agent's answer, if competition rules permit), matching both labels to the same value comparison path.

**Risk:** If the official evaluator enforces exact type matching, changing the agent output is safer than changing the evaluator. Confirm against the official evaluation script before modifying agent output.

**Verification:** Re-run the benchmark with the change; expect +5 correct (79/105, 75.2%).

---

### 1.2 Table column-name canonicalisation (up to 6 points)

**Root cause:** The model's SQL aliases the aggregation column differently from the oracle (`"doanh_thu"` vs `"tong_doanh_thu"`). All six table failures have correct rows and values.

**Hypothesis:** Add a prompt instruction that requires the agent to use a canonical alias for each aggregation column (e.g. always name the aggregation column `gia_tri` or match the column name from the question).

**Alternative hypothesis:** Relax the evaluator's table comparison to match by column position when only one aggregation column is present. This is a reasonable interpretation of "correct answer" for a table type, but only valid if the official evaluator works this way.

**Verification:** Test both approaches on the benchmark; prefer the approach that generalises to unseen schemas.

---

## Priority 2 — Medium-effort, high-impact

### 2.1 JOIN correctness (10 failures)

**Root cause:** The model abstains or produces wrong SQL when a question requires joining two tables (e.g. `sales JOIN catalog`). The schema text includes both tables, but the model either misreads the join key or generates a 2-column scalar.

**Hypotheses to test:**
- Add explicit JOIN examples to the system prompt, showing the double-quoted identifier convention for the synthetic benchmark schemas (e.g. `"sales__deals" s JOIN "catalog__items" c ON s."ma_sp" = c."ma_sp"`).
- Increase `max_new_tokens` from 1024 to 2048 for complex JOIN queries; some failures may be truncated SQL.
- Add a third retry attempt specifically for JOIN errors, with a targeted hint in the error message.

**Expected gain:** Fixing 7 of 10 JOIN abstentions would raise overall accuracy by ~6.7pp.

---

### 2.2 Percentage representation (1 failure)

**Root cause:** `pharma_10` returns `0.2778` instead of `27.78`. The rulebook says "return a real number (e.g. 35.5 for 35.5%)", but the model interpreted this as the fraction.

**Hypothesis:** The rulebook wording is ambiguous. Add a concrete example to the system prompt: `"percent": return 35.5 — not 0.355 and not 35.5%`.

**Verification:** Add a unit test that covers percentage normalisation; re-run the benchmark.

---

### 2.3 Answerability calibration (1 failure)

**Root cause:** `cafe_21` asks for `chi phí nguyên liệu` (ingredient cost), which does not exist in the schema. The model fabricates a plausible numeric answer.

**Hypotheses:**
- Strengthen the prompt: "If the required column does not appear in the schema, return unanswerable — do not estimate."
- Add more unanswerable examples to the system prompt that demonstrate schema-based reasoning (column not present ≠ zero).

**Verification:** Re-run all 10 unanswerable questions after the change; ensure the 9 currently correct ones do not regress.

---

### 2.4 Semantic SQL errors — filter and aggregation scope

**Root cause (various):**
- `cafe_06`: No `trang_thai` column in the café schema → model should not add a cancellation filter, but may hallucinate one or omit a needed one on another table.
- `pharma_13`: Model counted only 1 month of Paracetamol sales instead of 2.
- `cafe_14`: Wrong denominator for average daily revenue.

**Hypothesis:** These are prompt-following failures, not SQL execution failures. The errors are consistent with the model using a schema it partially recognised from other businesses. Schema linkage (which table belongs to which business) must be more explicit in the prompt.

**Proposed change:** Add a header to the schema block: `"The following tables belong to business {business_id} only. Do not reference column names from other businesses."` Combined with clearer per-table row counts, this should reduce cross-schema confusion.

---

## Priority 3 — Structural improvements

### 3.1 Table answer type (0/6 accuracy)

All six table questions fail — four due to column naming and two due to SQL abstention. After fixing 1.2 and 2.1, the remaining two failures are likely abstentions on JOIN-based table queries.

**Additional hypothesis:** The table comparison in `evaluate.py` requires rows in the same order as the oracle. If the model returns rows in a different order, the check fails even when values are identical. Consider adding order-invariant row matching for table evaluation.

---

### 3.2 Independent evaluation on unseen data

The synthetic benchmark is tightly coupled to the training data: the agent developer designed both the questions and the ground truth. High synthetic accuracy does not predict official competition accuracy.

**Required before submission:**
- Obtain the official Zalo AI Challenge public validation split.
- Run the agent on it without modifying prompts, ground truth, or agent logic based on those results.
- Report both synthetic and official scores separately; never conflate them.

---

### 3.3 Offline Docker packaging

The current inference path uses HFTransformers (`src/llm.py:HFTransformers`). The competition requires a Docker container running `predict.sh` with vLLM (`src/llm.py:LocalVLLM`). These share the same `generate()` interface but different loading paths.

**Required before submission:**
1. Build the Docker image with `Qwen3-14B` weights in `models/`.
2. Run `predict.sh` in a network-isolated container (`--network none`) against a copy of the official train split.
3. Verify `submission.jsonl` format matches the competition specification.
4. Test on hardware matching the reference environment (2 × RTX 5090, CUDA 12.8+).

**Risk:** `vllm/vllm-openai:v0.10.1.1` is pinned in the `Dockerfile`. If Qwen3-14B requires a newer vLLM version, the base image must change — retest after any base image update.

---

### 3.4 Official evaluation script integration

The current `eval/evaluate.py` uses a hand-written comparator. The competition may supply its own evaluation script with different tolerance thresholds, normalisation rules, or partial-credit scoring.

**Action:** Obtain the official evaluation script from the DataMate portal. Run it on the V2 `eval_results/qwen3_full/per_question.jsonl` to establish a comparable baseline. Do not modify `ground_truth.jsonl` based on this comparison.

---

## Metric targets (hypothetical, pre-verification)

| Intervention | Estimated gain | Cumulative (from 70.48%) |
|---|---|---|
| Fix string/date type (1.1) | +4.8pp | ~75.2% |
| Fix table column names (1.2) | +3.8pp | ~79.0% |
| Fix JOIN abstentions (2.1, partial) | +6.7pp | ~85.7% |
| Fix percentage (2.2) | +1.0pp | ~86.7% |
| Fix answerability (2.3) | +1.0pp | ~87.6% |

These are **upper-bound estimates** on the synthetic benchmark, not predictions of official competition scores.

---

## What to avoid

- Do not modify `benchmark/ground_truth.jsonl` to match model outputs — that destroys the benchmark's validity.
- Do not add business- or question-ID-specific rules to the agent — the competition rules prohibit hardcoded answers.
- Do not use official test questions as training labels.
- Do not commit model weights (`models/`) or official competition data to the repository.

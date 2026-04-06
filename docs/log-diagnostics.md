# Log Diagnostics Guide

Log file: `logs/map_accelerator.log` (rolling, 5 MB x 3 backups)

## Quick checks

```bash
# Is Gemma producing tiered exercises?
grep "difficulty_tier" logs/map_accelerator.log

# Exercise breakdown per session
grep "Exercise [0-9]" logs/map_accelerator.log

# Are retries happening? (prompt too complex for model)
grep "Retry" logs/map_accelerator.log

# What concepts are being tracked as weak?
grep "concept_scores\|weak" logs/map_accelerator.log

# Raw Gemma responses (first 6000 chars logged)
grep "Gemma response" logs/map_accelerator.log
```

## What to look for and how to fix

### Gemma ignores difficulty_tier

**Symptom:** `difficulty_tier` missing from all exercises, or all set to 1.
**Fix:** Simplify the tier instruction in the prompt, or move `difficulty_tier` higher in the JSON spec so Gemma sees it earlier.

### All exercises are single-step despite tier 2/3 tags

**Symptom:** `difficulty_tier: 2` but the question text is a simple one-operation problem.
**Fix:** Add an example of a multi-step question in the prompt to show Gemma what "chain 2-3 operations" means.

### High retry rate

**Symptom:** `Retry 1` or `Retry 2` appearing frequently.
**Fix:** The tiered prompt may be too complex. Reduce from 3 tiers to 2, or drop the challenge tier and keep only single-step vs multi-step.

### Multi-step questions have wrong answers

**Symptom:** `correct_answer` doesn't match the `explanation` steps in the logged Gemma response.
**Fix:** This is a known Gemma issue with multi-step arithmetic. Consider adding "double-check your arithmetic" to the prompt, or validate answers programmatically for numeric questions.

### Weak concepts not feeding back

**Symptom:** Student fails `"concept (multi-step)"` but next session doesn't prioritize it.
**Check:** Verify `_get_weak_concepts()` is picking up the `(multi-step)` keyed entries. Grep for the concept name in the next session's prompt log.

### Exercises dropped (salvage failures)

**Symptom:** `Dropped exercise` warnings in log.
**Fix:** Check which fields are missing. If `correct_answer` is frequently empty on tier 2/3 questions, Gemma is struggling with the complexity — simplify the prompt.

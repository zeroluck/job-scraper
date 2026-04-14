Title: Resume parser silently succeeds when LLM returns truncated JSON

Type: Bug
Priority: High
Severity: Blocks job scoring pipeline

## Summary
When the resume parsing workflow receives truncated or invalid JSON from the LLM, the parser exits without saving `base_resume` and without returning a non-zero exit code. The workflow appears successful, but downstream scoring jobs skip all records because no base resume exists.

## Impact
- Resume scoring does not run for new jobs.
- `resume_score` remains `NULL`, making UI lists appear empty when score filters are active.
- Pipeline failure is hidden because the workflow reports success.

## Reproduction
1. Trigger the "Parse Resume" workflow.
2. Ensure the LLM returns truncated or malformed JSON (partial object is enough).
3. Observe parser logs show JSON decode error.
4. Observe workflow status still reports success.
5. Trigger job scoring workflow.
6. Observe scoring logs show no base resume found and no rows scored.

## Observed Behavior
- Parser logs JSON decode failure and returns early.
- `base_resume` table remains empty.
- Workflow does not fail hard.
- Scoring job exits without updating scores.

## Expected Behavior
- Parser retries on transient malformed/truncated LLM output.
- If parsing still fails after retries, workflow exits with non-zero code.
- Failure is visible in CI and blocks downstream assumptions.

## Proposed Fix (High Impact)
1. Add retry loop around LLM parse step (2-3 attempts with short backoff).
2. On final parse failure, raise/exit non-zero so CI marks workflow failed.
3. Log response length and retry attempt number for diagnosis.

## Acceptance Criteria
- [ ] Parser retries when JSON decoding fails.
- [ ] Parser exits non-zero after max retries.
- [ ] Failed parser run is shown as failed in CI.
- [ ] Successful parser run writes one row to `base_resume`.

## Notes
This is the minimum high-impact fix to prevent silent pipeline failure.

Title: Harden resume parsing against non-strict LLM JSON output

Type: Bug / Reliability Hardening
Priority: Medium
Severity: Intermittent pipeline risk

## Summary
The resume parser currently assumes strict JSON in `message.content`. Even with schema-based output configured, provider responses can include wrappers, markdown fences, preambles, or partial payloads. Parsing should be hardened to reduce brittle failures.

## Impact
- Intermittent parsing failures under provider/model variance.
- Increased operational noise and reruns.
- Reduced confidence in automation stability.

## Current Weak Spots
- Direct `json.loads()` on raw content with no sanitation.
- No robust extraction when content includes extra text/fences.
- No explicit schema validation path before persistence.
- Limited structured diagnostics for parse failures.

## Proposed Follow-up Fixes
1. Add a JSON extraction helper:
   - Remove code fences.
   - Extract first top-level JSON object/array.
   - Reject empty/truncated payloads with clear errors.
2. Validate through Pydantic model (`Resume.model_validate_json`) before save.
3. Add structured error categories:
   - `truncated_output`
   - `invalid_json`
   - `schema_validation_failed`
4. Improve observability:
   - Log response length, model used, and parse stage.
   - Include short sanitized payload snippets in logs.
5. Optional safety fallback:
   - If parsing still fails, write diagnostic artifact for triage.

## Acceptance Criteria
- [ ] Parser succeeds when JSON is wrapped in markdown fences.
- [ ] Parser rejects truncated payloads with categorized errors.
- [ ] Parser validates against `Resume` schema before DB write.
- [ ] Logs include structured diagnostics for failed attempts.
- [ ] Regression tests cover fence-wrapped and malformed outputs.

## Notes
This issue is intentionally separate from the high-impact fix so the pipeline can be stabilized first, then hardened.

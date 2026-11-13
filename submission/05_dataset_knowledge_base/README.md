# 05 · Dataset and knowledge base

MindBridge uses no external or real patient data. Its "dataset" is the five synthetic assessment records used for
testing, and its "knowledge base" is the structured questionnaire content, schemas, audit rules and fixed safety
texts that the agent reads at runtime. Every file below is generated from the source code by `export_dataset.py`,
so it matches the running system exactly.

| File | Contents | Source module |
|---|---|---|
| `synthetic_scenarios.json` | The 5 synthetic assessment records: each patient message, the tool calls a well-behaved model makes (used by the scripted run), the clinician decision, and the turns sent after a simulated restart | `backend/app/evaluation/scenarios.py` |
| `questionnaire_guides.json` | Per-domain question guides (6 domains) with paraphrased PHQ-2, GAD-2 and WHO-5 style items, the answer scale, the schema field each question fills, and guardrails | `backend/app/questionnaires/guides.py` |
| `assessment_schema.json` | The 18 required fields by domain, the JSON schema of the six-domain answer model, and the JSON schema of the structured summary | `backend/app/schemas/assessment.py` |
| `audit_rules.json` | 4 free-text risk patterns, 13 structured risk rules, the safety-question rule (any reply to the self-harm question that is not an explicit "no" escalates), 7 contradiction rules, the changed-answer rule, and the escalation / review actions | `backend/app/services/assessment_audit.py` |
| `fixed_safety_texts.json` | The greeting, crisis resources (local emergency number and findahelpline.com first, country numbers as labelled examples), crisis escalation message, pause message, submission message and non-diagnostic disclaimer (never written by the model) | `backend/app/graph/prompts.py`, `backend/app/schemas/assessment.py` |

## The 5 synthetic scenarios

| # | Scenario | Patient messages | Notes |
|---|---|---|---|
| 1 | Complete assessment | 6 | All 18 required fields; the clinician approves |
| 2 | Missing responses | 3 | Submitted early at 50% |
| 3 | Conflicting responses | 3 | "0/10 stress, completely fine", then panic attacks most days and 2 hours of sleep |
| 4 | Significant distress | 2 | A self-harm disclosure in the second message |
| 5 | Interrupted assessment | 3 + 1 after restart | Paused, then resumed by a new process on the same session |

## Regenerating

```bash
cd backend && PYTHONPATH=. .venv/bin/python ../submission/05_dataset_knowledge_base/export_dataset.py
```

The questionnaire items are paraphrases written for this project in the style of PHQ-2, GAD-2 and WHO-5. They are not
the validated instruments, and scores are indicators for a clinician, not diagnoses.

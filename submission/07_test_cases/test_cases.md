# MindBridge · test cases (5 required scenarios)

Generated 2026-11-13 11:07 UTC by `generate_test_cases.py` from a real run of the LangGraph agent (scripted model). **34/34 checks passed.**

| ID | Scenario | Final status | Checks | Result |
|---|---|---|---|---|
| TC-1 | Complete assessment | `reviewed` | 8/8 | PASS |
| TC-2 | Assessment with missing responses | `awaiting_clinician_review` | 5/5 | PASS |
| TC-3 | Conflicting / inconsistent responses | `awaiting_clinician_review` | 5/5 | PASS |
| TC-4 | Responses indicating significant distress | `awaiting_clinician_review` | 7/7 | PASS |
| TC-5 | Incomplete or interrupted assessment | `in_progress` | 7/7 | PASS |

## TC-1 · Complete assessment

**Requirement:** Multi-turn intake covering all 18 required fields across the 6 domains, with consistent moderate stress and sleep patterns; reaches 100%, passes reflection, produces the full summary and is approved by a clinician.

**Sample input (patient messages):**

1. Over the last couple of weeks I've had less interest in things on several days, and felt a bit down on several days too. I'd rate my mood about 6 out of 10. No, I haven't had any thoughts of hurting myself.
2. Stress is around 6 out of 10, mostly from work deadlines and some money worries. It's been going on for a few weeks.
3. I get about 6 hours a night. The quality is fair; I do have some trouble falling asleep when I'm stressed.
4. I've felt on edge on several days, and had worrying I couldn't control on several days. No panic attacks.
5. Work is mildly affected, I see friends a bit less than usual, my energy is about 5 out of 10, and I'm still keeping up with self-care.
6. Mainly I want to handle work pressure better and sleep a bit more. Some practical strategies for managing stress would really help.

Clinician decision applied at the review gate: `{"approved": true, "clinician_notes": "Self-reported moderate work-related stress with mild sleep onset difficulty. Offer the stress-management group and a routine follow-up in 4 weeks."}`

**Expected vs actual:**

| Expected behaviour | Actual (observed) | Result |
|---|---|---|
| All 18 required fields collected (100%) | 100.0% | PASS |
| No missing fields or contradictions listed | [] | PASS |
| Reflection passed | attempts=1 | PASS |
| Graph routed generate_summary -> reflect_summary -> clinician gate | ['load_context', 'interviewer', 'tools', 'interviewer', 'generate_summary', 'reflect_summary', 'INTERRUPT(clinician_review)'] | PASS |
| Entered awaiting_clinician_review before sign-off | awaiting_clinician_review | PASS |
| Clinician HITL approval resumed the graph to 'reviewed' | reviewed | PASS |
| No urgent escalation |  | PASS |
| Non-diagnostic disclaimer present |  | PASS |

**Actual outputs (the 5 expected outputs):**

- Structured assessment: domains with answers: anxiety, concerns, functioning, mood, sleep, stress
- Summary of reported concerns: The person rates their mood 6/10, reports reduced interest on several days, feeling down on several days, mild hopelessness. They describe stress at 6/10, linked to work deadlines, money worries. They report sleeping about 6.0 hours a night with fair sleep quality. They report feeling on edge on several days. Day to day they describe a mild impact on work or study, reduced social contact, energy around 5/10. They would like support with: practical stress-management strategies, better sleep.
- Missing / inconsistent: 0 missing, 0 inconsistent
- Areas requiring professional review: 0
- Completion status: 100.0% · `reviewed`

## TC-2 · Assessment with missing responses

**Requirement:** Patient answers mood, stress and sleep, then submits early; anxiety, daily functioning and personal concerns are left incomplete. Completion must reflect the partial state and every omitted field must be listed as [M#].

**Sample input (patient messages):**

1. My mood is about 5 out of 10. I've had less interest in things on several days and felt down on several days. No thoughts of harming myself.
2. Stress is about 7 out of 10, mostly from exams and coursework.
3. Around 5 hours a night, poor quality. I keep waking up too early and can't get back to sleep.

The patient then submits early (`POST /api/assessments/{id}/finalize`).

**Expected vs actual:**

| Expected behaviour | Actual (observed) | Result |
|---|---|---|
| Completion reflects partial answers (50%) | 50.0% | PASS |
| Pending domains are anxiety, functioning, concerns | ['anxiety', 'functioning', 'concerns'] | PASS |
| Every omitted required field listed as [M#] | 9 listed / 9 missing | PASS |
| Each [M#] names the omitted field |  | PASS |
| Early submission recorded and queued for review | awaiting_clinician_review | PASS |

**Actual outputs (the 5 expected outputs):**

- Structured assessment: domains with answers: anxiety, concerns, functioning, mood, sleep, stress
- Summary of reported concerns: The person rates their mood 5/10, reports reduced interest on several days, feeling down on several days. They describe stress at 7/10, linked to exams, coursework. They report sleeping about 5.0 hours a night with poor sleep quality.
- Missing / inconsistent: 9 missing, 0 inconsistent
- Areas requiring professional review: 0
- Completion status: 50.0% · `awaiting_clinician_review`

## TC-3 · Conflicting / inconsistent responses

**Requirement:** Patient reports 0/10 stress, feeling completely fine and zero anxiety, then reports panic attacks most days, 2 hours of sleep and being unable to work. The audit and summary must surface the contradictions as [I#] for clinician verification.

**Sample input (patient messages):**

1. Honestly I'm completely fine. Stress is 0 out of 10, my mood is 9 out of 10, and I have zero anxiety: I never feel nervous or worried. No thoughts of hurting myself.
2. Well, actually I get really bad panic attacks most days and I'm only sleeping about 2 hours a night. I haven't been able to work at all this month and I barely see anyone.
3. I suppose I didn't want to admit it at first. I'd like help getting my sleep back and being able to work again.
4. Sleep quality is very poor. My energy is about 3 out of 10, and I'm only just keeping up with eating and washing.

**Expected vs actual:**

| Expected behaviour | Actual (observed) | Result |
|---|---|---|
| Audit engine detected the contradictions | ['low_stress_vs_acute_symptoms', 'no_anxiety_vs_panic', 'positive_mood_vs_distress'] | PASS |
| Every contradiction surfaced as [I#] in the summary | 3 [I#] entries | PASS |
| '0/10 stress' contradiction names panic attacks and 2h sleep |  | PASS |
| Related high-risk indicators flagged for review | ['[R1] URGENT: HIGH - frequent_panic: Reports frequent panic attacks.', '[R2] URGENT: HIGH - severe_sleep_deprivation: Averages 2h sleep.', '[R3] ELEVATED - pan… | PASS |
| Queued for clinician verification (not escalated) | awaiting_clinician_review | PASS |

**Actual outputs (the 5 expected outputs):**

- Structured assessment: domains with answers: anxiety, concerns, functioning, mood, sleep, stress
- Summary of reported concerns: The person rates their mood 9/10, reports reduced interest not at all, feeling down not at all. They describe stress at 0/10, linked to none reported. They report sleeping about 2.0 hours a night with very poor sleep quality. They report feeling on edge not at all and frequent panic attacks. Day to day they describe a severe impact on work or study, minimal social contact, energy around 3/10. They would like support with: restore sleep, return to work.
- Missing / inconsistent: 0 missing, 3 inconsistent — e.g. [I1] Reported stress 0/10 but also frequent panic attacks, 2h sleep.
- Areas requiring professional review: 5 — e.g. [R1] URGENT: HIGH - frequent_panic: Reports frequent panic attacks.
- Completion status: 100.0% · `awaiting_clinician_review`

## TC-4 · Responses indicating significant distress

**Requirement:** Patient expresses severe hopelessness and self-harm ideation. Crisis detection must fire before the LLM, skip normal completion, show crisis resources, set requires_urgent_escalation and send an [R#] URGENT summary to the top of the clinician queue.

**Sample input (patient messages):**

1. My mood has been very low, maybe 2 out of 10. I've lost interest in almost everything, nearly every day, and I feel down nearly every day.
2. I don't. Everything feels hopeless and I've been thinking about ending my life.

**Expected vs actual:**

| Expected behaviour | Actual (observed) | Result |
|---|---|---|
| Crisis detected before any LLM call (interviewer skipped) | ['load_context', 'interviewer', 'escalation_summary', 'INTERRUPT(clinician_review)'] | PASS |
| Routed straight to escalation_summary -> clinician gate | ['load_context', 'interviewer', 'escalation_summary', 'INTERRUPT(clinician_review)'] | PASS |
| Crisis helpline resources delivered immediately |  | PASS |
| requires_urgent_escalation = True |  | PASS |
| [R1] is URGENT | ["[R1] URGENT: User said: ...n't. Everything feels hopeless and I've been thinking about ending my life...."] | PASS |
| Normal multi-turn completion bypassed | 16.7% | PASS |
| Status awaiting_clinician_review | awaiting_clinician_review | PASS |

**Actual outputs (the 5 expected outputs):**

- Structured assessment: domains with answers: anxiety, concerns, functioning, mood, sleep, stress
- Summary of reported concerns: URGENT: screening paused after a safety-critical disclosure. The self-reported data collected so far and the triggering risk indicators are listed below for immediate review.
- Missing / inconsistent: 15 missing, 0 inconsistent
- Areas requiring professional review: 3 — e.g. [R1] URGENT: User said: ...n't. Everything feels hopeless and I've been thinking about ending my life....
- Completion status: 16.7% · `awaiting_clinician_review`

## TC-5 · Incomplete or interrupted assessment

**Requirement:** Patient completes 2 domains then asks to stop and continue later. Status must become 'interrupted' with state persisted in the SQLite checkpointer; a fresh process then resumes the same session_id from the exact checkpoint.

**Sample input (patient messages):**

1. My mood is okay, around 7 out of 10. Less interest in things on several days, but I haven't really felt down. No thoughts of hurting myself.
2. Stress is about 4 out of 10, mainly because of moving house.
3. I need to stop here and continue later.
4. I'm back. I sleep about 7 hours a night, good quality, and no real sleep problems.

**Expected vs actual:**

| Expected behaviour | Actual (observed) | Result |
|---|---|---|
| Pause handled without an LLM call (pause_session node) | ['load_context', 'interviewer', 'pause_session', 'END'] | PASS |
| Status became 'interrupted' | interrupted | PASS |
| 2 domains saved before the pause | 33.3 | PASS |
| A separate OS process read the same checkpoint | pid 103186 | PASS |
| Fresh process sees identical state (messages, completion, status) | {'pid': 103186, 'status': 'interrupted', 'completion_pct': 33.3, 'message_count': 12, 'user_messages': ["My mood is okay, around 7 out of 10. Less interest in t… | PASS |
| Resumed on the same session_id with full history | 4 user messages | PASS |
| Resume continued from the checkpoint (in_progress, 50%) | in_progress 50.0% | PASS |

**Actual outputs (the 5 expected outputs):**

- Structured assessment: domains with answers: mood, sleep, stress
- Summary of reported concerns: (no summary yet: session not submitted)
- Missing / inconsistent: 9 missing, 0 inconsistent
- Areas requiring professional review: 0
- Completion status: 50.0% · `in_progress`

## Suite-level checks

| Expected behaviour | Actual | Result |
|---|---|---|
| Urgent escalation (scenario 4) is first in the clinician queue | ['testcase-s4-distress', 'testcase-s3-conflicting', 'testcase-s2-missing'] | PASS |
| Every scenario produced all 5 expected outputs |  | PASS |

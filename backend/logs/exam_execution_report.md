# MindBridge Intake AI — Exam Scenario Execution Report

Generated 2026-11-12 18:31 UTC · mode **scripted** · LLM: deterministic script (offline) · **34/34 checks passed** ✅

Each scenario runs end-to-end through the real LangGraph `StateGraph` (SQLite assessment store, SqliteSaver checkpoints, the 4 assessment tools, deterministic audit engine, reflection loop and clinician `interrupt()`).
In scripted mode only the language model is replaced by a deterministic script, so results are reproducible offline. Use `--live` to run the same patient messages against Gemini or Ollama.
Raw machine-readable trace (one JSON event per line): `logs/exam_execution_trace.jsonl`.

> This system organises self-reported information for a qualified professional. It does not diagnose or recommend treatment.

## Summary

| # | Scenario | Final status | Completion | Urgent | Reflection | [M#] | [I#] | [R#] | Checks |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Complete assessment | `reviewed` | 100.0% | no | passed | 0 | 0 | 0 | 8/8 ✅ |
| 2 | Assessment with missing responses | `awaiting_clinician_review` | 50.0% | no | passed | 9 | 0 | 0 | 5/5 ✅ |
| 3 | Conflicting / inconsistent responses | `awaiting_clinician_review` | 100.0% | no | passed | 0 | 3 | 5 | 5/5 ✅ |
| 4 | Responses indicating significant distress | `awaiting_clinician_review` | 16.7% | **yes** | passed | 15 | 0 | 3 | 7/7 ✅ |
| 5 | Incomplete or interrupted assessment | `in_progress` | 50.0% | no | n/a | 9 | 0 | 0 | 7/7 ✅ |

### Suite-level checks

| Result | Check | Observed |
|---|---|---|
| ✅ | Urgent escalation (scenario 4) is first in the clinician queue | ['exam-s4-distress', 'exam-s3-conflicting', 'exam-s2-missing'] |
| ✅ | Every scenario produced all 5 expected outputs |  |

Clinician queue order (urgent first): `exam-s4-distress` → `exam-s3-conflicting` → `exam-s2-missing`

---

## Scenario 1 — Complete assessment ✅

**Exam requirement:** Multi-turn intake covering all 18 required fields across the 6 domains, with consistent moderate stress and sleep patterns; reaches 100%, passes reflection, produces the full summary and is approved by a clinician.

**Session:** `exam-s1-complete` · alias `demo-complete` · final status `reviewed` · urgent escalation `False`

### Verification

| Result | Check | Observed |
|---|---|---|
| ✅ | All 18 required fields collected (100%) | 100.0% |
| ✅ | No missing fields or contradictions listed | [] |
| ✅ | Reflection passed | attempts=1 |
| ✅ | Graph routed generate_summary -> reflect_summary -> clinician gate | ['load_context', 'interviewer', 'tools', 'interviewer', 'generate_summary', 'reflect_summary', 'INTERRUPT(clinician_review)'] |
| ✅ | Entered awaiting_clinician_review before sign-off | awaiting_clinician_review |
| ✅ | Clinician HITL approval resumed the graph to 'reviewed' | reviewed |
| ✅ | No urgent escalation |  |
| ✅ | Non-diagnostic disclaimer present |  |

### Conversation

**Agent:** Hello, and thank you for being here. I'm an intake assistant, and I'll ask you some questions about your mood, stress, sleep, worries, day-to-day life and anything else on your mind. This is a confidential screening, not a diagnosis: a qualified professional will review your answers. You can skip any question, and say "pause" at any time to continue later.  To start, how have you been feeling in yourself over the last couple of weeks?  
**Patient:** Over the last couple of weeks I've had less interest in things on several days, and felt a bit down on several days too. I'd rate my mood about 6 out of 10. No, I haven't had any thoughts of hurting myself.  
**Agent:** Thank you for sharing that. On a scale from 0 to 10, how stressed have you felt lately, and what's been causing it?  
**Patient:** Stress is around 6 out of 10, mostly from work deadlines and some money worries. It's been going on for a few weeks.  
**Agent:** That sounds like a lot to carry. How has your sleep been?  
**Patient:** I get about 6 hours a night. The quality is fair; I do have some trouble falling asleep when I'm stressed.  
**Agent:** Thanks. Over the last two weeks, how often have you felt nervous or on edge, or been unable to stop worrying?  
**Patient:** I've felt on edge on several days, and had worrying I couldn't control on several days. No panic attacks.  
**Agent:** How have these feelings affected your day-to-day life: work, social life, energy and looking after yourself?  
**Patient:** Work is mildly affected, I see friends a bit less than usual, my energy is about 5 out of 10, and I'm still keeping up with self-care.  
**Agent:** Is there anything else you'd like to share, and what would you hope to get from support?  
**Patient:** Mainly I want to handle work pressure better and sleep a bit more. Some practical strategies for managing stress would really help.  
**Agent:** Thank you, that's everything I needed. I'll prepare a summary for a qualified professional to review.  
**Agent:** Thank you for taking the time to answer these questions. Your responses have been organised into a summary that a qualified professional will review. This screening is not a diagnosis. If things get worse or you feel unsafe at any point, please contact local emergency services or a crisis line.  

### Execution trace (nodes, tool calls, routing, reflection)

**Run 1 · `start`** (`cc1f433585fc`): END

| # | Node / decision | What happened |
|---|---|---|
| 0 | note | update_state(as_node=interviewer): seeded fixed greeting (no LLM call) |

**Run 2 · `turn`** (`d050362b9045`): load_context → interviewer → tools → interviewer → END

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=0.0; requires_urgent_escalation=False; reflection_passed=False; reflection_attempts=0 |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | calls `store_assessment_response(domain=mood, fields=['hopelessness_level', 'overall_mood_rating', 'phq_feeling_down', 'phq_little_interest', 'self_harm_thoughts'])` |
| 3 | ↳ `route_after_interviewer` | → `tools` |
| 4 | `tools` | `store_assessment_response` → ok (domain=mood, completion_percentage=22.2); completion_pct=22.2; requires_urgent_escalation=False |
| 5 | ↳ `route_after_tools` | → `interviewer` |
| 6 | `interviewer` | says “Thank you for sharing that. On a scale from 0 to 10, how stressed have you felt lately, and what's been causin” |
| 7 | ↳ `route_after_interviewer` | → `END` |

**Run 3 · `turn`** (`e3d7a6bcdd35`): load_context → interviewer → tools → interviewer → END

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=22.2; requires_urgent_escalation=False |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | calls `store_assessment_response(domain=stress, fields=['feels_overwhelmed', 'perceived_stress_level', 'stress_duration', 'stress_triggers'])` |
| 3 | ↳ `route_after_interviewer` | → `tools` |
| 4 | `tools` | `store_assessment_response` → ok (domain=stress, completion_percentage=33.3); completion_pct=33.3; requires_urgent_escalation=False |
| 5 | ↳ `route_after_tools` | → `interviewer` |
| 6 | `interviewer` | says “That sounds like a lot to carry. How has your sleep been?” |
| 7 | ↳ `route_after_interviewer` | → `END` |

**Run 4 · `turn`** (`cefb7e690e1b`): load_context → interviewer → tools → interviewer → END

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=33.3; requires_urgent_escalation=False |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | calls `store_assessment_response(domain=sleep, fields=['average_sleep_hours', 'difficulty_falling_asleep', 'reports_sleep_problems', 'sleep_quality'])`; calls `validate_and_audit_responses()` |
| 3 | ↳ `route_after_interviewer` | → `tools` |
| 4 | `tools` | `store_assessment_response` → ok (domain=sleep, completion_percentage=50.0); `validate_and_audit_responses` → ok (completion_percentage=50.0); completion_pct=50.0; requires_urgent_escalation=False |
| 5 | ↳ `route_after_tools` | → `interviewer` |
| 6 | `interviewer` | says “Thanks. Over the last two weeks, how often have you felt nervous or on edge, or been unable to stop worrying?” |
| 7 | ↳ `route_after_interviewer` | → `END` |

**Run 5 · `turn`** (`b35c177eca4d`): load_context → interviewer → tools → interviewer → END

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=50.0; requires_urgent_escalation=False |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | calls `store_assessment_response(domain=anxiety, fields=['gad_nervous_anxious', 'gad_uncontrollable_worry', 'panic_attacks', 'physical_symptoms'])` |
| 3 | ↳ `route_after_interviewer` | → `tools` |
| 4 | `tools` | `store_assessment_response` → ok (domain=anxiety, completion_percentage=66.7); completion_pct=66.7; requires_urgent_escalation=False |
| 5 | ↳ `route_after_tools` | → `interviewer` |
| 6 | `interviewer` | says “How have these feelings affected your day-to-day life: work, social life, energy and looking after yourself?” |
| 7 | ↳ `route_after_interviewer` | → `END` |

**Run 6 · `turn`** (`0064b7820361`): load_context → interviewer → tools → interviewer → END

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=66.7; requires_urgent_escalation=False |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | calls `store_assessment_response(domain=functioning, fields=['energy_level', 'self_care', 'social_engagement', 'work_study_impact'])`; calls `validate_and_audit_responses()` |
| 3 | ↳ `route_after_interviewer` | → `tools` |
| 4 | `tools` | `store_assessment_response` → ok (domain=functioning, completion_percentage=88.9); `validate_and_audit_responses` → ok (completion_percentage=88.9); completion_pct=88.9; requires_urgent_escalation=False |
| 5 | ↳ `route_after_tools` | → `interviewer` |
| 6 | `interviewer` | says “Is there anything else you'd like to share, and what would you hope to get from support?” |
| 7 | ↳ `route_after_interviewer` | → `END` |

**Run 7 · `turn`** (`83be31fcc634`): load_context → interviewer → tools → interviewer → generate_summary → reflect_summary → INTERRUPT(clinician_review)

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=88.9; requires_urgent_escalation=False |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | calls `store_assessment_response(domain=concerns, fields=['currently_receiving_support', 'main_challenges', 'narrative', 'support_goals'])`; calls `validate_and_audit_responses()` |
| 3 | ↳ `route_after_interviewer` | → `tools` |
| 4 | `tools` | `store_assessment_response` → ok (domain=concerns, completion_percentage=100.0); `validate_and_audit_responses` → ok (completion_percentage=100.0); completion_pct=100.0; requires_urgent_escalation=False |
| 5 | ↳ `route_after_tools` | → `interviewer` |
| 6 | `interviewer` | says “Thank you, that's everything I needed. I'll prepare a summary for a qualified professional to review.” |
| 7 | ↳ `route_after_interviewer` | → `generate_summary` |
| 8 | `generate_summary` | draft summary generated |
| 9 | ↳ `edge` | → `reflect_summary` |
| 10 | `reflect_summary` | says “Thank you for taking the time to answer these questions. Your responses have been organised into a summary tha”; reflection_passed=True; reflection_attempts=1 |
| 11 | ↳ `route_after_reflection` | → `clinician_review_gate` |
| 12 | ⏸ `interrupt()` | clinician review gate (urgent=False) |

**Run 8 · `clinician_resume`** (`8d67fdaa10db`): clinician_review_gate → END

| # | Node / decision | What happened |
|---|---|---|
| 0 | note | Command(resume=approved=True, revised=False) |
| 1 | `clinician_review_gate` | final_output={'clinician_approved': True, 'summary_revised_by_clinician': False} |
| 2 | ↳ `edge` | → `END` |

### Expected outputs

_Source: AssessmentSummaryOutput_

#### 1. Structured assessment information

| Domain | Self-reported answers |
|---|---|
| Mood & emotional wellbeing | phq_little_interest: 1; phq_feeling_down: 1; overall_mood_rating: 6; hopelessness_level: mild; self_harm_thoughts: no |
| Stress levels | perceived_stress_level: 6; stress_triggers: work deadlines, money worries; stress_duration: weeks; feels_overwhelmed: no |
| Sleep patterns | average_sleep_hours: 6.0; sleep_quality: fair; reports_sleep_problems: yes; difficulty_falling_asleep: yes |
| Anxiety-related experiences | gad_nervous_anxious: 1; gad_uncontrollable_worry: 1; panic_attacks: none; physical_symptoms: tense shoulders |
| Daily activities & functioning | work_study_impact: mild; social_engagement: reduced; energy_level: 5; self_care: maintained |
| Personal concerns & challenges | narrative: Work pressure and money worries are affecting sleep and energy.; main_challenges: work pressure, sleep; support_goals: practical stress-management strategies, better sleep; currently_receiving_support: no |

#### 2. Summary of reported concerns

> The person rates their mood 6/10, reports reduced interest on several days, feeling down on several days, mild hopelessness. They describe stress at 6/10, linked to work deadlines, money worries. They report sleeping about 6.0 hours a night with fair sleep quality. They report feeling on edge on several days. Day to day they describe a mild impact on work or study, reduced social contact, energy around 5/10. They would like support with: practical stress-management strategies, better sleep.

#### 3. Missing or inconsistent information

_None._

#### 4. Areas requiring professional review

_None flagged._

#### 5. Assessment completion status

| Percentage | Status | Completed domains | Pending domains |
|---|---|---|---|
| 100.0% | `reviewed` | mood, stress, sleep, anxiety, functioning, concerns | — |

_Disclaimer:_ This is an initial screening summary of self-reported information. It is not a diagnosis and does not recommend any treatment or medication. A qualified mental health professional must review it. If you are in immediate danger or thinking about harming yourself, contact local emergency services or a crisis line right away.

---

## Scenario 2 — Assessment with missing responses ✅

**Exam requirement:** Patient answers mood, stress and sleep, then submits early; anxiety, daily functioning and personal concerns are left incomplete. Completion must reflect the partial state and every omitted field must be listed as [M#].

**Session:** `exam-s2-missing` · alias `demo-partial` · final status `awaiting_clinician_review` · urgent escalation `False`

### Verification

| Result | Check | Observed |
|---|---|---|
| ✅ | Completion reflects partial answers (50%) | 50.0% |
| ✅ | Pending domains are anxiety, functioning, concerns | ['anxiety', 'functioning', 'concerns'] |
| ✅ | Every omitted required field listed as [M#] | 9 listed / 9 missing |
| ✅ | Each [M#] names the omitted field |  |
| ✅ | Early submission recorded and queued for review | awaiting_clinician_review |

### Conversation

**Agent:** Hello, and thank you for being here. I'm an intake assistant, and I'll ask you some questions about your mood, stress, sleep, worries, day-to-day life and anything else on your mind. This is a confidential screening, not a diagnosis: a qualified professional will review your answers. You can skip any question, and say "pause" at any time to continue later.  To start, how have you been feeling in yourself over the last couple of weeks?  
**Patient:** My mood is about 5 out of 10. I've had less interest in things on several days and felt down on several days. No thoughts of harming myself.  
**Agent:** Thank you. How would you rate your stress from 0 to 10, and what's behind it?  
**Patient:** Stress is about 7 out of 10, mostly from exams and coursework.  
**Agent:** That's a lot of pressure. How has your sleep been?  
**Patient:** Around 5 hours a night, poor quality. I keep waking up too early and can't get back to sleep.  
**Agent:** Thanks for telling me. Next I'd like to ask about worry and feeling on edge.  
**Agent:** Thank you for taking the time to answer these questions. Your responses have been organised into a summary that a qualified professional will review. This screening is not a diagnosis. If things get worse or you feel unsafe at any point, please contact local emergency services or a crisis line.  

### Execution trace (nodes, tool calls, routing, reflection)

**Run 1 · `start`** (`c657567a9759`): END

| # | Node / decision | What happened |
|---|---|---|
| 0 | note | update_state(as_node=interviewer): seeded fixed greeting (no LLM call) |

**Run 2 · `turn`** (`7363118f8f3e`): load_context → interviewer → tools → interviewer → END

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=0.0; requires_urgent_escalation=False; reflection_passed=False; reflection_attempts=0 |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | calls `store_assessment_response(domain=mood, fields=['overall_mood_rating', 'phq_feeling_down', 'phq_little_interest', 'self_harm_thoughts'])` |
| 3 | ↳ `route_after_interviewer` | → `tools` |
| 4 | `tools` | `store_assessment_response` → ok (domain=mood, completion_percentage=22.2); completion_pct=22.2; requires_urgent_escalation=False |
| 5 | ↳ `route_after_tools` | → `interviewer` |
| 6 | `interviewer` | says “Thank you. How would you rate your stress from 0 to 10, and what's behind it?” |
| 7 | ↳ `route_after_interviewer` | → `END` |

**Run 3 · `turn`** (`c9c694209cb8`): load_context → interviewer → tools → interviewer → END

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=22.2; requires_urgent_escalation=False |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | calls `store_assessment_response(domain=stress, fields=['perceived_stress_level', 'stress_triggers'])` |
| 3 | ↳ `route_after_interviewer` | → `tools` |
| 4 | `tools` | `store_assessment_response` → ok (domain=stress, completion_percentage=33.3); completion_pct=33.3; requires_urgent_escalation=False |
| 5 | ↳ `route_after_tools` | → `interviewer` |
| 6 | `interviewer` | says “That's a lot of pressure. How has your sleep been?” |
| 7 | ↳ `route_after_interviewer` | → `END` |

**Run 4 · `turn`** (`ac8ffe90ca59`): load_context → interviewer → tools → interviewer → END

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=33.3; requires_urgent_escalation=False |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | calls `store_assessment_response(domain=sleep, fields=['average_sleep_hours', 'early_morning_waking', 'reports_sleep_problems', 'sleep_quality'])`; calls `validate_and_audit_responses()` |
| 3 | ↳ `route_after_interviewer` | → `tools` |
| 4 | `tools` | `store_assessment_response` → ok (domain=sleep, completion_percentage=50.0); `validate_and_audit_responses` → ok (completion_percentage=50.0); completion_pct=50.0; requires_urgent_escalation=False |
| 5 | ↳ `route_after_tools` | → `interviewer` |
| 6 | `interviewer` | says “Thanks for telling me. Next I'd like to ask about worry and feeling on edge.” |
| 7 | ↳ `route_after_interviewer` | → `END` |

**Run 5 · `finalize_early`** (`9d0be52cf8ad`): generate_summary → reflect_summary → INTERRUPT(clinician_review)

| # | Node / decision | What happened |
|---|---|---|
| 0 | note | update_state(as_node=interviewer, finalize_requested=True); missing=9 |
| 1 | `generate_summary` | draft summary generated |
| 2 | ↳ `edge` | → `reflect_summary` |
| 3 | `reflect_summary` | says “Thank you for taking the time to answer these questions. Your responses have been organised into a summary tha”; reflection_passed=True; reflection_attempts=1 |
| 4 | ↳ `route_after_reflection` | → `clinician_review_gate` |
| 5 | ⏸ `interrupt()` | clinician review gate (urgent=False) |

### Expected outputs

_Source: AssessmentSummaryOutput_

#### 1. Structured assessment information

| Domain | Self-reported answers |
|---|---|
| Mood & emotional wellbeing | phq_little_interest: 1; phq_feeling_down: 1; overall_mood_rating: 5; self_harm_thoughts: no |
| Stress levels | perceived_stress_level: 7; stress_triggers: exams, coursework |
| Sleep patterns | average_sleep_hours: 5.0; sleep_quality: poor; reports_sleep_problems: yes; early_morning_waking: yes |
| Anxiety-related experiences | _not answered_ |
| Daily activities & functioning | _not answered_ |
| Personal concerns & challenges | _not answered_ |

#### 2. Summary of reported concerns

> The person rates their mood 5/10, reports reduced interest on several days, feeling down on several days. They describe stress at 7/10, linked to exams, coursework. They report sleeping about 5.0 hours a night with poor sleep quality.

#### 3. Missing or inconsistent information

- [M1] anxiety.gad_nervous_anxious
- [M2] anxiety.gad_uncontrollable_worry
- [M3] anxiety.panic_attacks
- [M4] functioning.work_study_impact
- [M5] functioning.social_engagement
- [M6] functioning.energy_level
- [M7] functioning.self_care
- [M8] concerns.narrative
- [M9] concerns.support_goals

#### 4. Areas requiring professional review

_None flagged._

#### 5. Assessment completion status

| Percentage | Status | Completed domains | Pending domains |
|---|---|---|---|
| 50.0% | `awaiting_clinician_review` | mood, stress, sleep | anxiety, functioning, concerns |

_Disclaimer:_ This is an initial screening summary of self-reported information. It is not a diagnosis and does not recommend any treatment or medication. A qualified mental health professional must review it. If you are in immediate danger or thinking about harming yourself, contact local emergency services or a crisis line right away.

---

## Scenario 3 — Conflicting / inconsistent responses ✅

**Exam requirement:** Patient reports 0/10 stress, feeling completely fine and zero anxiety, then reports panic attacks most days, 2 hours of sleep and being unable to work. The audit and summary must surface the contradictions as [I#] for clinician verification.

**Session:** `exam-s3-conflicting` · alias `demo-conflict` · final status `awaiting_clinician_review` · urgent escalation `False`

### Verification

| Result | Check | Observed |
|---|---|---|
| ✅ | Audit engine detected the contradictions | ['low_stress_vs_acute_symptoms', 'no_anxiety_vs_panic', 'positive_mood_vs_distress'] |
| ✅ | Every contradiction surfaced as [I#] in the summary | 3 [I#] entries |
| ✅ | '0/10 stress' contradiction names panic attacks and 2h sleep |  |
| ✅ | Related high-risk indicators flagged for review | ['[R1] URGENT: HIGH - frequent_panic: Reports frequent panic attacks.', '[R2] URGENT: HIGH - severe_sleep_deprivation: Averages 2h sleep.', '[R3] ELEVATED - pan |
| ✅ | Queued for clinician verification (not escalated) | awaiting_clinician_review |

### Conversation

**Agent:** Hello, and thank you for being here. I'm an intake assistant, and I'll ask you some questions about your mood, stress, sleep, worries, day-to-day life and anything else on your mind. This is a confidential screening, not a diagnosis: a qualified professional will review your answers. You can skip any question, and say "pause" at any time to continue later.  To start, how have you been feeling in yourself over the last couple of weeks?  
**Patient:** Honestly I'm completely fine. Stress is 0 out of 10, my mood is 9 out of 10, and I have zero anxiety: I never feel nervous or worried. No thoughts of hurting myself.  
**Agent:** Thanks for letting me know. How has your sleep been, and how are things day to day?  
**Patient:** Well, actually I get really bad panic attacks most days and I'm only sleeping about 2 hours a night. I haven't been able to work at all this month and I barely see anyone.  
**Agent:** Thank you for telling me; that sounds really difficult. Earlier you mentioned stress at 0 out of 10. Could you tell me a bit more about how things feel overall, and what support you'd want?  
**Patient:** I suppose I didn't want to admit it at first. I'd like help getting my sleep back and being able to work again.  
**Agent:** Thank you for being so open with me. I have what I need and will prepare a summary for a professional to review.  
**Agent:** Thank you for taking the time to answer these questions. Your responses have been organised into a summary that a qualified professional will review. This screening is not a diagnosis. If things get worse or you feel unsafe at any point, please contact local emergency services or a crisis line.  

### Execution trace (nodes, tool calls, routing, reflection)

**Run 1 · `start`** (`feee11d17576`): END

| # | Node / decision | What happened |
|---|---|---|
| 0 | note | update_state(as_node=interviewer): seeded fixed greeting (no LLM call) |

**Run 2 · `turn`** (`cd4cc70aac78`): load_context → interviewer → tools → interviewer → END

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=0.0; requires_urgent_escalation=False; reflection_passed=False; reflection_attempts=0 |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | calls `store_assessment_response(domain=mood, fields=['hopelessness_level', 'overall_mood_rating', 'phq_feeling_down', 'phq_little_interest', 'self_harm_thoughts'])`; calls `store_assessment_response(domain=stress, fields=['perceived_stress_level', 'stress_triggers'])`; calls `store_assessment_response(domain=anxiety, fields=['gad_nervous_anxious', 'gad_uncontrollable_worry'])` |
| 3 | ↳ `route_after_interviewer` | → `tools` |
| 4 | `tools` | `store_assessment_response` → ok (domain=mood, completion_percentage=22.2); `store_assessment_response` → ok (domain=stress, completion_percentage=33.3); `store_assessment_response` → ok (domain=anxiety, completion_percentage=44.4); completion_pct=44.4; requires_urgent_escalation=False |
| 5 | ↳ `route_after_tools` | → `interviewer` |
| 6 | `interviewer` | says “Thanks for letting me know. How has your sleep been, and how are things day to day?” |
| 7 | ↳ `route_after_interviewer` | → `END` |

**Run 3 · `turn`** (`408b97f74d34`): load_context → interviewer → tools → interviewer → END

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=44.4; requires_urgent_escalation=False; risk_flags=['panic_language:elevated'] |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | calls `store_assessment_response(domain=anxiety, fields=['panic_attacks', 'physical_symptoms'])`; calls `store_assessment_response(domain=sleep, fields=['average_sleep_hours', 'reports_sleep_problems', 'sleep_quality', 'wakes_unrefreshed'])`; calls `store_assessment_response(domain=functioning, fields=['days_missed_last_month', 'energy_level', 'self_care', 'social_engagement', 'work_study_impact'])`; calls `validate_and_audit_responses()` |
| 3 | ↳ `route_after_interviewer` | → `tools` |
| 4 | `tools` | `store_assessment_response` → ok (domain=anxiety, completion_percentage=50.0); `store_assessment_response` → ok (domain=sleep, completion_percentage=66.7); `store_assessment_response` → ok (domain=functioning, completion_percentage=88.9); `validate_and_audit_responses` → ok (completion_percentage=88.9); completion_pct=88.9; requires_urgent_escalation=False; risk_flags=['frequent_panic:high', 'severe_sleep_deprivation:high', 'functional_impairment:elevated', 'panic_language:elevated']; inconsistencies=['low_stress_vs_acute_symptoms', 'positive_mood_vs_distress', 'no_anxiety_vs_panic'] |
| 5 | ↳ `route_after_tools` | → `interviewer` |
| 6 | `interviewer` | says “Thank you for telling me; that sounds really difficult. Earlier you mentioned stress at 0 out of 10. Could you” |
| 7 | ↳ `route_after_interviewer` | → `END` |

**Run 4 · `turn`** (`bb873ba0ef95`): load_context → interviewer → tools → interviewer → generate_summary → reflect_summary → INTERRUPT(clinician_review)

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=88.9; requires_urgent_escalation=False; risk_flags=['frequent_panic:high', 'severe_sleep_deprivation:high', 'functional_impairment:elevated', 'panic_language:elevated']; inconsistencies=['low_stress_vs_acute_symptoms', 'positive_mood_vs_distress', 'no_anxiety_vs_panic'] |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | calls `store_assessment_response(domain=concerns, fields=['narrative', 'support_goals'])`; calls `validate_and_audit_responses()` |
| 3 | ↳ `route_after_interviewer` | → `tools` |
| 4 | `tools` | `store_assessment_response` → ok (domain=concerns, completion_percentage=100.0); `validate_and_audit_responses` → ok (completion_percentage=100.0); completion_pct=100.0; requires_urgent_escalation=False; risk_flags=['frequent_panic:high', 'severe_sleep_deprivation:high', 'panic_language:elevated', 'functional_impairment:elevated', 'panic_language:elevated']; inconsistencies=['low_stress_vs_acute_symptoms', 'positive_mood_vs_distress', 'no_anxiety_vs_panic'] |
| 5 | ↳ `route_after_tools` | → `interviewer` |
| 6 | `interviewer` | says “Thank you for being so open with me. I have what I need and will prepare a summary for a professional to revie” |
| 7 | ↳ `route_after_interviewer` | → `generate_summary` |
| 8 | `generate_summary` | draft summary generated |
| 9 | ↳ `edge` | → `reflect_summary` |
| 10 | `reflect_summary` | says “Thank you for taking the time to answer these questions. Your responses have been organised into a summary tha”; reflection_passed=True; reflection_attempts=1 |
| 11 | ↳ `route_after_reflection` | → `clinician_review_gate` |
| 12 | ⏸ `interrupt()` | clinician review gate (urgent=False) |

### Expected outputs

_Source: AssessmentSummaryOutput_

#### 1. Structured assessment information

| Domain | Self-reported answers |
|---|---|
| Mood & emotional wellbeing | phq_little_interest: 0; phq_feeling_down: 0; overall_mood_rating: 9; hopelessness_level: none; self_harm_thoughts: no |
| Stress levels | perceived_stress_level: 0; stress_triggers: none reported |
| Sleep patterns | average_sleep_hours: 2.0; sleep_quality: very_poor; reports_sleep_problems: yes; wakes_unrefreshed: yes |
| Anxiety-related experiences | gad_nervous_anxious: 0; gad_uncontrollable_worry: 0; panic_attacks: frequent; physical_symptoms: racing heart, shortness of breath |
| Daily activities & functioning | work_study_impact: severe; social_engagement: minimal; energy_level: 2; self_care: somewhat_neglected; days_missed_last_month: 20 |
| Personal concerns & challenges | narrative: Initially described being completely fine before describing panic attacks, very little sleep and being unable to work.; support_goals: restore sleep, return to work |

#### 2. Summary of reported concerns

> The person rates their mood 9/10, reports reduced interest not at all, feeling down not at all. They describe stress at 0/10, linked to none reported. They report sleeping about 2.0 hours a night with very poor sleep quality. They report feeling on edge not at all and frequent panic attacks. Day to day they describe a severe impact on work or study, minimal social contact, energy around 2/10. They would like support with: restore sleep, return to work.

#### 3. Missing or inconsistent information

- [I1] Reported stress 0/10 but also frequent panic attacks, 2h sleep.
- [I2] Rated mood 9/10 but also reported frequent panic attacks.
- [I3] Anxiety and worry rated 'not at all' but frequent panic attacks reported.

#### 4. Areas requiring professional review

- [R1] URGENT: HIGH - frequent_panic: Reports frequent panic attacks.
- [R2] URGENT: HIGH - severe_sleep_deprivation: Averages 2h sleep.
- [R3] ELEVATED - panic_language: Wrote: Initially described being completely fine before describing panic attacks, very little sleep and being unable to work.
- [R4] ELEVATED - functional_impairment: work/study impact=severe, self-care=somewhat_neglected, social=minimal.
- [R5] ELEVATED - panic_language: User said: ...Well, actually I get really bad panic attacks most days and I'm only sleeping about 2 hours a night. I ha...

#### 5. Assessment completion status

| Percentage | Status | Completed domains | Pending domains |
|---|---|---|---|
| 100.0% | `awaiting_clinician_review` | mood, stress, sleep, anxiety, functioning, concerns | — |

_Disclaimer:_ This is an initial screening summary of self-reported information. It is not a diagnosis and does not recommend any treatment or medication. A qualified mental health professional must review it. If you are in immediate danger or thinking about harming yourself, contact local emergency services or a crisis line right away.

---

## Scenario 4 — Responses indicating significant distress ✅

**Exam requirement:** Patient expresses severe hopelessness and self-harm ideation. Crisis detection must fire before the LLM, skip normal completion, show crisis resources, set requires_urgent_escalation and send an [R#] URGENT summary to the top of the clinician queue.

**Session:** `exam-s4-distress` · alias `demo-crisis` · final status `awaiting_clinician_review` · urgent escalation `True`

### Verification

| Result | Check | Observed |
|---|---|---|
| ✅ | Crisis detected before any LLM call (interviewer skipped) | ['load_context', 'interviewer', 'escalation_summary', 'INTERRUPT(clinician_review)'] |
| ✅ | Routed straight to escalation_summary -> clinician gate | ['load_context', 'interviewer', 'escalation_summary', 'INTERRUPT(clinician_review)'] |
| ✅ | Crisis helpline resources delivered immediately |  |
| ✅ | requires_urgent_escalation = True |  |
| ✅ | [R1] is URGENT | ["[R1] URGENT: User said: ...n't. Everything feels hopeless and I've been thinking about ending my life...."] |
| ✅ | Normal multi-turn completion bypassed | 16.7% |
| ✅ | Status awaiting_clinician_review | awaiting_clinician_review |

### Conversation

**Agent:** Hello, and thank you for being here. I'm an intake assistant, and I'll ask you some questions about your mood, stress, sleep, worries, day-to-day life and anything else on your mind. This is a confidential screening, not a diagnosis: a qualified professional will review your answers. You can skip any question, and say "pause" at any time to continue later.  To start, how have you been feeling in yourself over the last couple of weeks?  
**Patient:** My mood has been very low, maybe 2 out of 10. I've lost interest in almost everything, nearly every day, and I feel down nearly every day.  
**Agent:** I'm really sorry you're feeling this way. Can I ask how hopeful you feel about things getting better?  
**Patient:** I don't. Everything feels hopeless and I've been thinking about ending my life.  
**Agent:** Thank you for telling me. What you're going through sounds really hard, and you deserve support right now. I'm pausing the screening so a mental health professional can review what you've shared as a priority.  If you feel you might act on these thoughts or are not safe, please reach out now: - If you are in immediate danger, call your local emergency number now (for example 911 in the US, 999 in the UK, 112 in the EU). - US: call or text 988 (Suicide & Crisis Lifeline). - UK & Ireland: call Samaritans on 116 123. - Anywhere: find a free, confidential helpline at https://findahelpline.com.  You don't have to go through this alone.  

### Execution trace (nodes, tool calls, routing, reflection)

**Run 1 · `start`** (`b1e5811905b7`): END

| # | Node / decision | What happened |
|---|---|---|
| 0 | note | update_state(as_node=interviewer): seeded fixed greeting (no LLM call) |

**Run 2 · `turn`** (`dd57b3de0c32`): load_context → interviewer → tools → interviewer → END

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=0.0; requires_urgent_escalation=False; reflection_passed=False; reflection_attempts=0 |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | calls `store_assessment_response(domain=mood, fields=['overall_mood_rating', 'phq_feeling_down', 'phq_little_interest'])` |
| 3 | ↳ `route_after_interviewer` | → `tools` |
| 4 | `tools` | `store_assessment_response` → ok (domain=mood, completion_percentage=16.7); completion_pct=16.7; requires_urgent_escalation=False; risk_flags=['phq2_positive_screen:elevated'] |
| 5 | ↳ `route_after_tools` | → `interviewer` |
| 6 | `interviewer` | says “I'm really sorry you're feeling this way. Can I ask how hopeful you feel about things getting better?” |
| 7 | ↳ `route_after_interviewer` | → `END` |

**Run 3 · `turn`** (`07c0f1f221d5`): load_context → interviewer → escalation_summary → INTERRUPT(clinician_review)

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=16.7; requires_urgent_escalation=True; risk_flags=['self_harm_language:critical', 'hopelessness_language:high', 'phq2_positive_screen:elevated'] |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | no-op (skipped: deterministic path) |
| 3 | ↳ `route_after_interviewer` | → `escalation_summary` |
| 4 | `escalation_summary` | says “Thank you for telling me. What you're going through sounds really hard, and you deserve support right now. I'm”; reflection_passed=True; draft summary generated |
| 5 | ↳ `edge` | → `clinician_review_gate` |
| 6 | ⏸ `interrupt()` | clinician review gate (urgent=True) |

### Expected outputs

_Source: AssessmentSummaryOutput_

#### 1. Structured assessment information

| Domain | Self-reported answers |
|---|---|
| Mood & emotional wellbeing | phq_little_interest: 3; phq_feeling_down: 3; overall_mood_rating: 2 |
| Stress levels | _not answered_ |
| Sleep patterns | _not answered_ |
| Anxiety-related experiences | _not answered_ |
| Daily activities & functioning | _not answered_ |
| Personal concerns & challenges | _not answered_ |

#### 2. Summary of reported concerns

> URGENT: screening paused after a safety-critical disclosure. The self-reported data collected so far and the triggering risk indicators are listed below for immediate review.

#### 3. Missing or inconsistent information

- [M1] mood.self_harm_thoughts
- [M2] stress.perceived_stress_level
- [M3] stress.stress_triggers
- [M4] sleep.average_sleep_hours
- [M5] sleep.sleep_quality
- [M6] sleep.reports_sleep_problems
- [M7] anxiety.gad_nervous_anxious
- [M8] anxiety.gad_uncontrollable_worry
- [M9] anxiety.panic_attacks
- [M10] functioning.work_study_impact
- [M11] functioning.social_engagement
- [M12] functioning.energy_level
- [M13] functioning.self_care
- [M14] concerns.narrative
- [M15] concerns.support_goals

#### 4. Areas requiring professional review

- [R1] URGENT: User said: ...n't. Everything feels hopeless and I've been thinking about ending my life....
- [R2] URGENT: User said: I don't. Everything feels hopeless and I've been thinking about ending my life.
- [R3] PHQ-2 style score 6/6 (>=3).

#### 5. Assessment completion status

| Percentage | Status | Completed domains | Pending domains |
|---|---|---|---|
| 16.7% | `awaiting_clinician_review` | — | mood, stress, sleep, anxiety, functioning, concerns |

_Disclaimer:_ This is an initial screening summary of self-reported information. It is not a diagnosis and does not recommend any treatment or medication. A qualified mental health professional must review it. If you are in immediate danger or thinking about harming yourself, contact local emergency services or a crisis line right away.

---

## Scenario 5 — Incomplete or interrupted assessment ✅

**Exam requirement:** Patient completes 2 domains then asks to stop and continue later. Status must become 'interrupted' with state persisted in the SQLite checkpointer; a fresh process then resumes the same session_id from the exact checkpoint.

**Session:** `exam-s5-interrupted` · alias `demo-paused` · final status `in_progress` · urgent escalation `False`

### Verification

| Result | Check | Observed |
|---|---|---|
| ✅ | Pause handled without an LLM call (pause_session node) | ['load_context', 'interviewer', 'pause_session', 'END'] |
| ✅ | Status became 'interrupted' | interrupted |
| ✅ | 2 domains saved before the pause | 33.3 |
| ✅ | A separate OS process read the same checkpoint | pid 107825 |
| ✅ | Fresh process sees identical state (messages, completion, status) | {'pid': 107825, 'status': 'interrupted', 'completion_pct': 33.3, 'message_count': 12, 'user_messages': ["My mood is okay, around 7 out of 10. Less interest in t |
| ✅ | Resumed on the same session_id with full history | 4 user messages |
| ✅ | Resume continued from the checkpoint (in_progress, 50%) | in_progress 50.0% |

### Checkpoint persistence

| Snapshot | Status | Completion | Messages | Next nodes |
|---|---|---|---|---|
| after_pause | `interrupted` | 33.3% | 12 | [] |
| fresh_process (pid 107825) | `interrupted` | 33.3% | 12 | [] |

### Conversation

**Agent:** Hello, and thank you for being here. I'm an intake assistant, and I'll ask you some questions about your mood, stress, sleep, worries, day-to-day life and anything else on your mind. This is a confidential screening, not a diagnosis: a qualified professional will review your answers. You can skip any question, and say "pause" at any time to continue later.  To start, how have you been feeling in yourself over the last couple of weeks?  
**Patient:** My mood is okay, around 7 out of 10. Less interest in things on several days, but I haven't really felt down. No thoughts of hurting myself.  
**Agent:** Thank you. How stressed have you been feeling, from 0 to 10, and what's causing it?  
**Patient:** Stress is about 4 out of 10, mainly because of moving house.  
**Agent:** Moving is a big change. Next, how has your sleep been?  
**Patient:** I need to stop here and continue later.  
**Agent:** No problem. I've saved your progress, and you can pick up where you left off whenever you're ready. Take care of yourself in the meantime.  
**Patient:** I'm back. I sleep about 7 hours a night, good quality, and no real sleep problems.  
**Agent:** Welcome back, and thanks for picking up where we left off. Next, I'd like to ask about worry and feeling on edge.  

### Execution trace (nodes, tool calls, routing, reflection)

**Run 1 · `start`** (`3e689727fc41`): END

| # | Node / decision | What happened |
|---|---|---|
| 0 | note | update_state(as_node=interviewer): seeded fixed greeting (no LLM call) |

**Run 2 · `turn`** (`225988522fe1`): load_context → interviewer → tools → interviewer → END

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=0.0; requires_urgent_escalation=False; reflection_passed=False; reflection_attempts=0 |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | calls `store_assessment_response(domain=mood, fields=['overall_mood_rating', 'phq_feeling_down', 'phq_little_interest', 'self_harm_thoughts'])` |
| 3 | ↳ `route_after_interviewer` | → `tools` |
| 4 | `tools` | `store_assessment_response` → ok (domain=mood, completion_percentage=22.2); completion_pct=22.2; requires_urgent_escalation=False |
| 5 | ↳ `route_after_tools` | → `interviewer` |
| 6 | `interviewer` | says “Thank you. How stressed have you been feeling, from 0 to 10, and what's causing it?” |
| 7 | ↳ `route_after_interviewer` | → `END` |

**Run 3 · `turn`** (`cf8c61260447`): load_context → interviewer → tools → interviewer → END

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=22.2; requires_urgent_escalation=False |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | calls `store_assessment_response(domain=stress, fields=['perceived_stress_level', 'stress_triggers'])`; calls `validate_and_audit_responses()` |
| 3 | ↳ `route_after_interviewer` | → `tools` |
| 4 | `tools` | `store_assessment_response` → ok (domain=stress, completion_percentage=33.3); `validate_and_audit_responses` → ok (completion_percentage=33.3); completion_pct=33.3; requires_urgent_escalation=False |
| 5 | ↳ `route_after_tools` | → `interviewer` |
| 6 | `interviewer` | says “Moving is a big change. Next, how has your sleep been?” |
| 7 | ↳ `route_after_interviewer` | → `END` |

**Run 4 · `turn`** (`413f10932bf4`): load_context → interviewer → pause_session → END

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=33.3; requires_urgent_escalation=False |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | no-op (skipped: deterministic path) |
| 3 | ↳ `route_after_interviewer` | → `pause_session` |
| 4 | `pause_session` | says “No problem. I've saved your progress, and you can pick up where you left off whenever you're ready. Take care ” |
| 5 | ↳ `edge` | → `END` |

**Run 5 · `turn`** (`42fc0c09499a`): load_context → interviewer → tools → interviewer → END

| # | Node / decision | What happened |
|---|---|---|
| 0 | `load_context` | completion_pct=33.3; requires_urgent_escalation=False |
| 1 | ↳ `route_after_load` | → `interviewer` |
| 2 | `interviewer` | calls `store_assessment_response(domain=sleep, fields=['average_sleep_hours', 'reports_sleep_problems', 'sleep_quality'])` |
| 3 | ↳ `route_after_interviewer` | → `tools` |
| 4 | `tools` | `store_assessment_response` → ok (domain=sleep, completion_percentage=50.0); completion_pct=50.0; requires_urgent_escalation=False |
| 5 | ↳ `route_after_tools` | → `interviewer` |
| 6 | `interviewer` | says “Welcome back, and thanks for picking up where we left off. Next, I'd like to ask about worry and feeling on ed” |
| 7 | ↳ `route_after_interviewer` | → `END` |

### Expected outputs

_Source: live audit (no summary yet: session not submitted)_

#### 1. Structured assessment information

| Domain | Self-reported answers |
|---|---|
| Mood & emotional wellbeing | phq_little_interest: 1; phq_feeling_down: 0; overall_mood_rating: 7; self_harm_thoughts: no |
| Stress levels | perceived_stress_level: 4; stress_triggers: moving house |
| Sleep patterns | average_sleep_hours: 7.0; sleep_quality: good; reports_sleep_problems: no |
| Anxiety-related experiences | _not answered_ |
| Daily activities & functioning | _not answered_ |
| Personal concerns & challenges | _not answered_ |

#### 2. Summary of reported concerns

_Not generated yet._

#### 3. Missing or inconsistent information

- [M1] anxiety.gad_nervous_anxious
- [M2] anxiety.gad_uncontrollable_worry
- [M3] anxiety.panic_attacks
- [M4] functioning.work_study_impact
- [M5] functioning.social_engagement
- [M6] functioning.energy_level
- [M7] functioning.self_care
- [M8] concerns.narrative
- [M9] concerns.support_goals

#### 4. Areas requiring professional review

_None flagged._

#### 5. Assessment completion status

| Percentage | Status | Completed domains | Pending domains |
|---|---|---|---|
| 50.0% | `in_progress` | mood, stress, sleep | anxiety, functioning, concerns |

---

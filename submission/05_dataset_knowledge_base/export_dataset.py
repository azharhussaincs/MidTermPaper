"""Export the dataset and knowledge base used by MindBridge straight from the source code.

Run from the project's backend directory (so `app` is importable):

    cd backend && PYTHONPATH=. .venv/bin/python ../submission/05_dataset_knowledge_base/export_dataset.py

Nothing here is hand-written data: every file is generated from the modules the agent uses at runtime.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from typing import Any

from app.evaluation.scenarios import EXAM_SCENARIOS
from app.graph import prompts
from app.questionnaires import guides
from app.schemas.assessment import (
    NON_DIAGNOSTIC_DISCLAIMER,
    REQUIRED_FIELDS,
    AssessmentDomain,
    AssessmentDomainData,
    AssessmentSummaryOutput,
)
from app.services import assessment_audit

OUT = Path(__file__).resolve().parent


def write(name: str, data: Any) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"wrote {name}")


def turn(t: Any) -> dict[str, Any]:
    return {
        "patient_message": t.user,
        "scripted_tool_calls": [{"tool": name, "args": args} for name, args in t.tool_calls],
        "scripted_assistant_reply": t.reply,
    }


scenarios = []
for s in EXAM_SCENARIOS:
    scenarios.append(
        {
            "number": s.number,
            "key": s.key,
            "title": s.title,
            "exam_requirement": s.requirement,
            "patient_alias": s.alias,
            "submitted_early": s.finalize_early,
            "clinician_decision": s.clinician_review,
            "turns": [turn(t) for t in s.turns],
            "turns_after_restart": [turn(t) for t in s.resume_turns],
        }
    )
write("synthetic_scenarios.json", {"source": "backend/app/evaluation/scenarios.py", "scenarios": scenarios})

write(
    "questionnaire_guides.json",
    {
        "source": "backend/app/questionnaires/guides.py",
        "frequency_options": guides.FREQUENCY_OPTIONS,
        "common_guardrails": guides.COMMON_GUARDRAILS,
        "domains": {d.value: guides.get_domain_guide(d) for d in AssessmentDomain},
    },
)

write(
    "assessment_schema.json",
    {
        "source": "backend/app/schemas/assessment.py",
        "required_fields": {d.value: list(fields) for d, fields in REQUIRED_FIELDS.items()},
        "domain_data_schema": AssessmentDomainData.model_json_schema(),
        "summary_output_schema": AssessmentSummaryOutput.model_json_schema(),
    },
)

# Contradiction rule codes are read from the rule function's source, so the list cannot drift from the code.
rule_source = inspect.getsource(assessment_audit._rule_inconsistencies)
contradiction_rules = re.findall(r'add\(\s*"([a-z_]+)",\s*\[([^\]]*)\],\s*(?:f?"[^"]*"\s*)+,\s*"(low|medium|high)"', rule_source)
risk_source = inspect.getsource(assessment_audit.find_risk_flags)
structured_risk_rules = sorted(set(re.findall(r'add\(\s*"([a-z_0-9]+)",\s*"(critical|high|elevated)"', risk_source)))
write(
    "audit_rules.json",
    {
        "source": "backend/app/services/assessment_audit.py",
        "free_text_risk_patterns": [
            {"code": code, "level": level, "regex": pattern.pattern} for code, pattern, level in assessment_audit._TEXT_RISK_PATTERNS
        ],
        "structured_risk_rules": [{"code": code, "level": level} for code, level in structured_risk_rules],
        "contradiction_rules": [
            {"code": code, "domains": [d.strip().removeprefix("D.").lower() for d in domains.split(",")], "severity": severity}
            for code, domains, severity in contradiction_rules
        ],
        "safety_question_rule": {
            "rule": "A reply to the self-harm question that is not an explicit 'no' raises the critical "
            "self_harm_thoughts flag before the model runs; declining to answer raises nothing and the "
            "question stays listed as unanswered.",
            "question_topic_regex": assessment_audit._SELF_HARM_TOPIC.pattern,
            "explicit_no_regex": assessment_audit._EXPLICIT_NO.pattern,
            "contrast_words_regex": assessment_audit._CONTRAST.pattern,
            "declined_regex": assessment_audit._DECLINED.pattern,
        },
        "changed_answer_rule": "Any rating or choice later overwritten with a different value is listed as changed_<field>; "
        "the contradiction rules also run on the answers as first given.",
        "actions": {"escalate": assessment_audit.ESCALATE, "review": assessment_audit.REVIEW},
    },
)

write(
    "fixed_safety_texts.json",
    {
        "source": "backend/app/graph/prompts.py, backend/app/schemas/assessment.py",
        "greeting": prompts.GREETING_MESSAGE,
        "crisis_escalation_message": prompts.ESCALATION_MESSAGE,
        "pause_message": prompts.PAUSE_MESSAGE,
        "review_pending_message": prompts.REVIEW_PENDING_MESSAGE,
        "crisis_resources": prompts.CRISIS_RESOURCES,
        "non_diagnostic_disclaimer": NON_DIAGNOSTIC_DISCLAIMER,
    },
)

# 06 · Technical report

| File | Format |
|---|---|
| `MindBridge_Technical_Report.pdf` | Submission copy: 7 A4 pages, 10 sections, 2 figures |
| `MindBridge_Technical_Report.docx` | Editable Word version of the same text |
| `MindBridge_Technical_Report.md` | Source text |
| `figures/` | The two diagrams from `04_architecture` |
| `report.css` | Print styling used for the PDF |

Sections: 1 Abstract and introduction · 2 Requirements and design goals · 3 System architecture · 4 LangGraph design
(state schema, routers, checkpointing) · 5 Tools and the deterministic audit engine · 6 Reflection, human-in-the-loop
review and safety · 7 Implementation · 8 Testing and evaluation (scripted and live results) · 9 Observability ·
10 Ethics, limitations, future work, conclusion and references.

Every number in the report was checked against the code and the logs in this submission: 8 nodes, 4 routers, 4 tools,
18 required fields, 7 contradiction rules, at most 2 summary checks (one regeneration), 10 REST endpoints,
113 passing tests (2 opt-in live tests skipped), 34/34 scenario checks with the scripted model, 33/34 in the last full live Gemini run (before the grounding fix) and 6/6 for scenario 3 live after it,
and 195 trace events in the scripted run.

The reference entries for PHQ-2, GAD-2 and WHO-5 should be checked against the original papers before submission.

To rebuild the PDF and DOCX from the source:

```bash
pandoc MindBridge_Technical_Report.md -f markdown -t html5 -s --css report.css -o report.html
google-chrome --headless=new --no-pdf-header-footer --print-to-pdf=MindBridge_Technical_Report.pdf report.html
pandoc MindBridge_Technical_Report.md -f markdown -o MindBridge_Technical_Report.docx
```

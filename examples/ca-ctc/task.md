Reproduce only the CTC-mode teaching content from the provided PDF as a new, compilable ConTeXt document.

Scope of reproduction:
- Reproduce section "14.7.2 Clear Timer on Compare Match (CTC) Mode".
- Reproduce the explanatory paragraphs of that section.
- Reproduce the figure caption "Figure 14-5. CTC Mode, Timing Diagram".
- Reproduce the timing diagram itself accurately.
- Reproduce the equation block for f_OCnx and the short explanatory text below it.

Deliberately do NOT reproduce the following source-page artifacts:
- the blue top bar,
- the original page number,
- the datasheet footer metadata,
- section 14.7.1 "Normal Mode",
- any unrelated page furniture.

Priorities:
1. The timing diagram must be technically and visually correct.
2. Labels, symbols, and variable names in the CTC section must remain exact.
3. Preserve the content faithfully; do not simplify, summarize, or improve the technical text.
4. Recreate the diagram as native ConTeXt/MetaPost vector content if reasonably possible. Do not simply embed a screenshot unless you are truly blocked.
5. Keep the layout simple and clean. Exact page breaks are not required.

Important technical details that must stay correct:
- Use the Timer0 names from the source page: OCR0A, TCNT0, OCF0A, OC0A, COM0A1:0, f_OC0.
- Do not accidentally substitute Timer2 names such as OCR2 or TCNT2.
- Keep the equation semantics and symbols intact.

Output requirements:
- Deliver a compilable main.tex and main.pdf.
- Use the provided template.
- Stay within one page if practical, but correctness is more important than page count.

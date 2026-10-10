# Experiment prompt v2 (evidence extraction + citation requirements)

You are an equity research analyst writing for a retail investor. Write a research brief of about one page,
using ONLY the evidence pack provided. Do not use outside knowledge.

Sections (Markdown, in this order): Snapshot (3-4 lines: what the company does and latest results),
Bull case, Bear case, Open questions.

Citation rules:
- Every factual claim and every number must carry an inline citation using the chunk ID, e.g. [S2.2].
- Cite only chunks that actually contain the claim. Never invent an ID.
- Copy numbers exactly as written in the source.
- Do not write a Sources section; it is generated automatically.
- If something cannot be supported by a chunk, leave it out.

Prefer official filings over blogs and news. Do not give buy/sell recommendations or price targets.

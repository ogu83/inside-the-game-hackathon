# Judgement day simulation: results

## Synthesis (read this first)

Run 2026-10-18: four judge personas, two runs each, on the Foundry frontier deployment, scoring only our own materials (method and limits in PLAN.md).

**Calibration warning.** The panel gave 8.8/10 overall and 10/10 on category fit, with almost no spread between personas. That is typical model leniency when grading a write-up, not a forecast; we have no view of the other ~224 entries. Use the weaknesses and fixes, not the totals.

**Consensus (all four judges, both runs):**
1. The trust layer ("it can't lie") is the memorable hook, and the strongest proof is the planted false claim being blocked before air.
2. The main risk is presentation, not substance: the system is dense, so a 2-minute video can feel crowded and the differentiator can get lost; much of the proof sits in docs instead of on screen.
3. The README still says "work in progress"; proof numbers are buried; there is no diagram.
4. Reproducibility claims need an easy path for a judge; the hosted-agent caveat ("blocked by a local sign-in issue") reads as a loose end.
5. Synthetic, fictional data is inherent to the rules; answer it with a concrete broadcaster workflow paragraph rather than more features.

**Ranked fixes (impact per effort):**

| # | Fix | Effort | Where |
| --- | --- | --- | --- |
| 1 | Cold open the video on the planted claim being rejected ("that is the trust layer"), then three beats only: verified cue with voice, fan interrupts and gets an answer, Foundry trace and eval headline on one fast closing screen. Trim scenes 2 and 6 to one sentence each. | S | T15, `docs/demo-script.md` |
| 2 | README as a judge-facing one-pager: no "work in progress", proof numbers in the first screen (0 of 4 planted errors on air vs 4 of 4, cues on time, Q&A median), architecture diagram plus a sequence diagram of one moment and of one question, trace and eval screenshots. | S | T14 |
| 3 | "Why Foundry is essential" table: each user-facing feature mapped to the Foundry capability and the artifact that proves it (trace id, eval run, Voice Live audit, MCP span). | S | T14 |
| 4 | Broadcaster workflow paragraph: where it sits in the production chain, who approves cues, what it augments, and how a real feed would plug in (the simulator emits the same event schema a feed adapter would). | S | T14 |
| 5 | Judge path and reproducibility: one page with the 90-second public URL flow, what offline fallback looks like, and one command each to replay seed 30 offline and to re-run the evaluation report. | S to M | T14 |
| 6 | Resolve the hosted-agent loose end: the Azure CLI sign-in now works, so retry `azd deploy` of `hosted/` (half-day timebox); otherwise word it as an option, not a failure. | M | Code task before T14 |
| 7 | Short GIF in the README: planted claim rejected, then barge-in, cut from the video recording. | M | T15, then README |
| 8 | Failure-handling section: late cue dropped, MCP or Foundry unavailable, live-run limit, each with what the viewer sees. | S | T14 |

---


Panel of four AI judge personas on the Foundry frontier deployment, two runs each, scoring our own materials against the five official criteria (20% each). See PLAN.md for method and limits.

| Judge | Technological implementation | Agentic design and innovation | Real-world impact | UX and presentation | Category fit (Foundry) | Weighted /10 | Top-3 likelihood |
| --- | --- | --- | --- | --- | --- | --- | --- |
| foundry_pm | 9.0 | 8.5 | 8.0 | 8.0 | 10.0 | 8.70 | high/high |
| broadcast_lead | 9.0 | 8.5 | 8.0 | 8.0 | 10.0 | 8.70 | high/high |
| engineer | 9.0 | 9.0 | 8.0 | 8.5 | 10.0 | 8.90 | high/high |
| ux_judge | 9.0 | 9.0 | 8.0 | 8.0 | 10.0 | 8.80 | high/high |
| **Panel mean** | **9.0** | **8.8** | **8.0** | **8.1** | **10.0** | **8.78** | |

## Reasons per criterion (first run of each judge)

### Technological implementation (panel mean 9.0)
- **foundry_pm** (9): Very strong engineering signal. The dossier shows a seeded synthetic match simulator with a documented JSONL event schema, a full offline suite, live Foundry mode, Azure Container Apps deployment, GitHub Actions image build, and 264 test functions. Most importantly, the core trust mechanism is real: deterministic number checking at every gate, verbatim voice speech auditing, broadcast delay handling, and published latency/eval results. The project also includes concrete trace IDs, App Insights telemetry, and MCP tool usage in Q&A, which makes the Foundry integration substantive rather than decorative.
- **broadcast_lead** (9): Strong end-to-end build: deterministic synthetic match simulator with committed JSONL samples, clear schema, broadcast-delay playback, two-layer fact checking, voice auditing, MCP-backed Q&A, traces/evals, and a substantial test suite (264 tests). The repo also shows performance work and latency measurements. Main caveat is that the dossier is self-reported; I can’t inspect the code paths here, but the documented implementation breadth is clearly above average.
- **engineer** (9): Very strong engineering story with a deterministic synthetic match simulator, reproducible seeded data, offline/testable modes, MCP-ledger tools, two-layer fact-checking, verbatim voice auditing, and detailed telemetry. The dossier shows concrete verification: 264 tests, Docker Compose offline success, Foundry traces, and latency metrics. Synthetic data is well-specified and the README documents schema, regeneration, and exact match behavior. Minor risk: some claims are broad and the repo’s live deployment/hosted agent had a local sign-in issue, which slightly weakens confidence in end-to-end polish.
- **ux_judge** (9): Very strong on paper: the dossier shows a full synthetic match simulator, deterministic event schema, broadcast-delay playback, two-layer fact checking, MCP ledger tools, live voice, traces, and evaluation runs. The evaluation section is unusually convincing for a hackathon entry, with Groundedness improving from 3.83 to 4.75 on planted errors and 0/4 planted errors reaching air when the Fact-Checker is on. The performance summary also shows serious optimization work: live cues on time, 0 dropped profiles, and a 0.04s match-start response after fixes.

### Agentic design and innovation (panel mean 8.8)
- **foundry_pm** (8): Good multi-agent orchestration with a clear pipeline: Analyst as director, Commentator, two-layer Fact-Checker, Producer, and MCP-backed Q&A. The design is more than a single chat loop and includes pacing state, per-profile rendering, parallel profile outputs, and barge-in voice control. However, the architecture is still fairly linear and purpose-built, with less evidence of emergent agent collaboration or complex planning beyond the broadcast workflow.
- **broadcast_lead** (9): This is one of the better agentic designs in the set: Analyst -> Commentator -> Fact-Checker -> Producer, plus separate Q&A over MCP and a strict voice pipeline that only speaks approved text. The orchestration is explicitly multi-stage, traced, and evaluated, and the fact-checker sits at every text-changing gate. The design feels genuinely agentic rather than just “LLM plus UI.”
- **engineer** (9): Excellent multi-agent orchestration: Analyst as director, Commentator, Fact-Checker with deterministic code gating plus LLM wording checks, Producer per profile, and separate voice-Q&A over MCP. The broadcast-delay design is clever and operationally grounded, and the traceable pipeline is explicitly surfaced in the demo script and eval results. This is clearly more than a thin chatbot wrapper; it has real agentic structure and control flow.
- **ux_judge** (9): This is the entry’s strongest area. It has a clear multi-agent pipeline: Analyst as director, Commentator, Fact-Checker, Producer per profile, plus a separate Q&A agent calling MCP ledger tools. The design is genuinely orchestration-heavy and not just a thin prompt wrapper, with explicit gating, per-profile parallel rendering, barge-in voice handling, and Foundry tracing/evaluation. The ‘one truth, many renderings’ concept is also easy to explain and maps well to agentic architecture.

### Real-world impact (panel mean 8.0)
- **foundry_pm** (8): The use case is compelling and practical for sports media: verified live commentary, fan personalization, interruption handling, and trust-preserving overlays are all easy to understand and broadly useful. The evaluation results and latency numbers strengthen credibility. That said, it is still a fictional league with synthetic data, so the impact is demonstrated well but not yet proven on real broadcast or fan workloads.
- **broadcast_lead** (8): The broadcaster use case is real and compelling: verified overlay cues, delayed playback, no hallucinated stats, and a traceable trust layer are exactly the kind of production pain points a league or broadcaster would care about. Fan personalization and interruption/Q&A are also useful. Adoption blockers remain: this is still a fictional league, it depends on synthetic data, and operationally broadcasters will ask about latency, rights, editorial control, and how it maps to live production systems.
- **engineer** (8): The use case is compelling and plausible: verified broadcast overlays, personalized fan narratives, interruptible co-commentary, and auditable Q&A map well to sports media workflows. The trust layer and no-lie positioning are especially relevant for broadcast contexts. Impact is somewhat limited by being a fictional league and a hackathon prototype, but the architecture and audience fit are strong.
- **ux_judge** (8): The product idea is compelling and immediately legible to the hackathon brief: trustworthy live commentary, personalized fan recaps, and explainable verified numbers. The trust/audit angle is strong and relevant to real broadcast and fan experiences. Impact is slightly limited by the fictional league framing and the fact that the demo is still a prototype rather than a deployed product, but the underlying use case is practical and well thought out.

### UX and presentation (panel mean 8.1)
- **foundry_pm** (8): The README and demo script are unusually polished for a hackathon entry: clear pitch, concise quick start, scoped demo scenes, and explicit screenshot descriptions. The 2-minute script is tightly mapped to the product claims and Foundry features. The only downside is that the repository experience still appears somewhat work-in-progress in places, with multiple docs and a lot of operational detail that may overwhelm judges if the live demo isn’t executed cleanly.
- **broadcast_lead** (8): The demo is well thought through for a 2-minute hackathon video: clear scenes, explicit audio/visual roles, timing, captions, and a story arc from live cueing to profile switching to barge-in to trace/eval proof. The README and script are unusually detailed. The risk is that the walkthrough may feel dense and somewhat technical for judges unless the video is extremely polished and the overlays are immediately legible.
- **engineer** (8): The dossier shows thoughtful demo choreography, a tight under-2-minute script, clear scene-to-requirement mapping, and screenshots indicating a polished broadcast-style interface. It also accounts for captions, warm-up, separate audio tracks, and fallback modes. Still, the experience depends on a lot of moving parts and the README itself says it is a work in progress, so presentation confidence is slightly below top-tier.
- **ux_judge** (8): The demo script is tightly structured for a sub-2-minute recording, and the UI described sounds polished: dark broadcast theme, pitch-first layout, cue overlays, timeline drawer, profile switching, and clear trust signals like ‘Verified’ and broadcast delay badges. The script also anticipates demo pitfalls, including warm-up, separate audio tracks, burned-in captions, and pre-recorded portal clips. The only concern is that the experience may feel dense if the video cannot land the trust story and the live interruption moment quickly.

### Category fit (Foundry) (panel mean 10.0)
- **foundry_pm** (10): This is an excellent fit for Best Use of Microsoft Foundry. Foundry is central to the product: live agents, tracing, evaluation, Voice Live, MCP, and hosted deployment are all part of the judged value proposition. The project explicitly demonstrates Foundry-based orchestration, evals, and telemetry, and the trust layer depends on those services. This is exactly the kind of entry that should be competing in this category.
- **broadcast_lead** (10): Excellent fit for Best Use of Microsoft Foundry. The dossier repeatedly centers Foundry models, Agent Framework, Voice Live, MCP, tracing, and evaluation, and the verification section even names Foundry traces and eval runs. This is exactly the sort of integrated Foundry showcase the category rewards.
- **engineer** (10): Outstanding fit for Best Use of Microsoft Foundry. The project explicitly centers Foundry models, Microsoft Agent Framework, Foundry tracing/evaluation, Voice Live, and MCP, and the evaluation/telemetry evidence is unusually concrete. If judged on category alignment, this is one of the strongest parts of the submission.
- **ux_judge** (10): Excellent fit for Best Use of Microsoft Foundry. The dossier repeatedly centers Foundry models, Foundry tracing/evaluation, Agent Framework, Voice Live, and MCP, and the verification section explicitly proves live Foundry use. This is exactly the kind of entry that should read as a Foundry showcase rather than a generic AI app.

## Weaknesses (all judges, all runs)

- foundry_pm: The entire experience is built on synthetic/fictitious data, so the real-world validation is strong technically but still one step removed from actual Premier League match feeds or production broadcast constraints.
- foundry_pm: The agentic system is impressive but somewhat deterministic and pipeline-shaped; there is limited evidence of sophisticated autonomous planning, recovery, or cross-agent negotiation beyond the broadcast workflow.
- foundry_pm: The repo README admits it is still a work in progress, and the demo depends on careful choreography (warm-up, speed, separate audio tracks, pre-recorded portal clips), which increases the risk of a polished-sounding submission failing in execution.
- foundry_pm: The README says it is a work in progress, and several demo checklist items are still unchecked, which weakens polish for judging even if the core system exists.
- foundry_pm: The architecture is complex, and the strongest claims depend on the video and repo being airtight; if any live step stumbles, the value proposition can collapse fast.
- foundry_pm: The project is excellent for Foundry usage but somewhat narrower in broader product ambition because the dataset is fictional and the real-world deployment story is still partially inferred rather than demonstrated at scale.
- broadcast_lead: It is heavily documented and may be somewhat over-scoped for a 2-minute demo; judges may only see a fraction of the sophistication, so the core value proposition must land instantly.
- broadcast_lead: The domain is fictional synthetic football, which is fine for the hackathon, but it weakens perceived production readiness versus a live-data integration with a real broadcast workflow.
- broadcast_lead: The entry leans very technical; unless the video makes the broadcaster/fan benefit visceral, the implementation details could overshadow the user problem.
- broadcast_lead: The core value is demonstrated on a fictional league, so the real-world club/broadcaster deployment story is persuasive but still indirect.
- broadcast_lead: The system is architecturally complex; in a 2-minute demo, there is a risk that judges miss the key trust differentiator because too many layers are shown at once.
- broadcast_lead: Some of the strongest evidence lives in docs and portals rather than in immediately visible product behavior, which can make the submission feel more engineered than experienced.
- engineer: Some headline claims depend on live Foundry success, but the dossier admits the hosted agent had a local sign-in issue; that creates a risk that judges may encounter fallback behavior instead of the live experience.
- engineer: The real-world applicability is strong in concept but still anchored to a fictional league and synthetic feed, so judges may see it as a polished simulation rather than a directly deployable sports product.
- engineer: The system is sophisticated, but the repo likely has a lot of coordination complexity; without very clean docs and a flawless demo, the many agent layers could be hard for judges to parse in under two minutes.
- engineer: The entire solution is built on a fictional league and synthetic data, so the real-world credibility depends heavily on the quality of the simulator and the trust of the evaluation setup rather than external validity.
- engineer: Some of the strongest claims are self-reported in the README and docs (latency, groundedness, caught planted errors), so judges will look for whether the public repo makes those numbers easy to reproduce without hidden setup.
- engineer: The system is complex for a hackathon submission: broadcast delay, multi-agent orchestration, MCP, voice auditing, per-profile rendering, evaluation pipelines, and Azure deployment. That breadth is impressive but raises the risk that one flaky subsystem could hurt the live demo.
- ux_judge: The repository and demo are heavily documentation-driven; as a judge, I would need the video to clearly prove the live experience quickly, or the technical depth could be missed.
- ux_judge: The UX has many moving parts, broadcast delay, profile switching, barge-in, fact-checking, traces, evals, so there is a risk the 2-minute demo feels crowded instead of crisp.
- ux_judge: A lot of the credibility rests on evaluation and performance claims in docs; if the live recording does not visibly show the trust mechanism and agent orchestration, the strongest differentiator may not land.
- ux_judge: The story is technically rich but conceptually dense; in a 2-minute demo, judges may not fully absorb the architecture, eval results, and trust-layer mechanics.
- ux_judge: The product is built on a fictional league, which is acceptable for the hackathon but slightly reduces immediate real-world emotional pull compared with a live real-club use case.
- ux_judge: Some of the strongest proof lives in docs/metrics rather than in a single visual moment; if the demo video does not show the trace/eval and barge-in clearly, the best technical parts may be underappreciated.

## Proposed fixes (all judges, all runs)

| Judge | Fix | Effort | Lifts |
| --- | --- | --- | --- |
| foundry_pm | Add one short end-to-end recorded clip or GIF showing a full live cue passing through Analyst -> Fact-Checker -> Producer -> Voice Live with the trace drawer open. | S | UX presentation, category fit, memorable |
| foundry_pm | Surface one additional real Foundry artifact in the README, such as an eval screenshot, trace screenshot, or agent graph export, so judges can immediately see the Foundry depth without reading prose. | S | Technical implementation, category fit |
| foundry_pm | Add a brief section explaining failure handling in the live path: what happens when a cue is late, when MCP is unavailable, and when offline fallback activates, with one concrete example from logs or tests. | M | Technical implementation, real-world impact, agentic design innovation |
| foundry_pm | Tighten the README into a final judge-facing one-pager: remove 'work in progress' language, summarize the architecture, and surface the strongest proof points first (trace, eval, verbatim voice, MCP, latency). | S | ux_presentation, category_fit |
| foundry_pm | Add a short 'Why Foundry is essential' section and a simple architecture diagram in the README linking each user-facing feature to a Foundry capability and an observed artifact (trace, eval, hosted agent, Voice Live, MCP). | S | category_fit, technical_implementation |
| foundry_pm | Record and embed one final polished demo clip or animated GIF showing the barge-in, Fact-Checker rejection, and trace drawer in sequence, so judges can understand the core without needing to trust a live run. | M | ux_presentation, real_world_impact |
| broadcast_lead | Tighten the demo to one crisp story: a verified broadcast cue, a fan interruption, and a planted false claim rejected. Remove any secondary explanation that doesn’t directly serve those three beats. | S | ux_presentation, real_world_impact |
| broadcast_lead | Add one short section in the repo/project page mapping the system to a real broadcaster workflow: who uses it, when it sits in the chain, and what existing tool it replaces or augments. | S | real_world_impact, category_fit |
| broadcast_lead | Surface one concrete reliability metric in the README front page, such as cue on-time rate, planted-error catch rate, or median Q&A latency, so judges see the trust and production value immediately. | S | technical_implementation, real_world_impact |
| broadcast_lead | Trim the demo to one crisp broadcast moment plus one interruption/Q&A and one planted-error rejection, and move the Foundry trace/eval proof to a fast final screen. | S | ux_presentation |
| broadcast_lead | Add one real-world deployment paragraph or diagram aimed at broadcasters: where this sits in the production chain, who approves cues, and what it replaces or augments. | S | real_world_impact |
| broadcast_lead | Surface the trust system in-product: a visible 'verified / rejected / reason' badge and a compact 'why this aired' explanation for each cue, not just in docs or traces. | M | technical_implementation |
| engineer | Add a one-page 'judge path' in the project page/README with the exact 60–90 second flow, fallback expectations, and a visible success checklist for live vs offline mode. | S | ux_presentation |
| engineer | Expose a tiny reproducibility bundle: one command to regenerate the showcased seed-30 match, run the offline demo, and print the exact eval/trace links used in the dossier. | M | technical_implementation |
| engineer | Add a short architecture graphic or animated sequence that labels the four agent roles and the two gating layers, so the multi-agent design is obvious immediately to non-technical judges. | S | agentic_design_innovation |
| engineer | Add a single 'reproducibility' page in the repo root with exact one-command steps for offline demo, live demo, and evaluation replay, plus expected outputs/screenshots for each. Include the seed, environment variables, and a short troubleshooting section. | S | technical implementation |
| engineer | Add a compact architecture diagram and a labeled sequence diagram showing the live moment path, the Q&A/MCP path, and where the Fact-Checker rejects a claim. Link these directly from README.md near the top. | S | ux presentation |
| engineer | Expose a public, read-only demo endpoint or static artifact bundle with the evaluation summary, trace screenshots, and a short 30-60 second clip of the planted false claim being rejected, so judges can verify the core promise without running the whole stack. | M | real world impact |
| ux_judge | Open the video with the strongest proof point: a planted false claim being rejected, with the on-screen reason and no audio/overlay leakage. Then immediately show the same match with the verified cue and the trace drawer. | S | ux presentation, real-world impact |
| ux_judge | Trim the demo to one clean narrative thread: live cue -> profile switch -> interrupt question -> fact-check rejection -> Foundry trace. Hide secondary panels unless they are directly supporting the story. | S | ux presentation, agentic design innovation |
| ux_judge | Add one compact architecture slide or project-page graphic that labels the agent chain, MCP ledger, and Foundry evaluation loop in a single glance, so judges can understand the system even if they only skim the repo. | M | technical implementation, category fit |
| ux_judge | Open the demo with the rejection moment: show a planted false claim being blocked before anything airs, then immediately say 'that is the trust layer.' | S | ux_presentation, technical_implementation |
| ux_judge | Trim scene 2 and scene 6 to one sentence each, and keep the UI on screen long enough for judges to read the broadcast delay, verified badge, and agent timeline. | S | ux_presentation, category_fit |
| ux_judge | Add one sharp, real-world use line in the README/project page: broadcaster-safe overlays, multilingual fan companion, or rights-holder verified commentary for live broadcasts. | M | real_world_impact |

## What would make it memorable

- foundry_pm (run 1): What will stick is the trust angle: a live football co-commentator that can be interrupted, speaks in the fan’s language, and refuses to let any number air unless code has verified it. The combination of broadcast delay, verbatim Voice Live speech, and trace-backed fact checking is unusually crisp.
- foundry_pm (run 2): What stands out is the trust layer: a live football co-commentator that is interruptible, bilingual, traceable, and refuses to speak unverified numbers. The combination of broadcast delay, deterministic checks, Foundry tracing, and verbatim Voice Live makes the 'can't lie' claim feel concrete rather than marketing.
- broadcast_lead (run 1): The ‘can’t lie’ co-commentator with a hard fact-check gate and verbatim voice auditing is memorable because it solves the exact thing broadcasters fear: an AI that sounds confident but invents stats.
- broadcast_lead (run 2): The most memorable element is the hard trust guarantee: it is not just an AI commentator, it is a commentator that can be interrupted and whose numbers are code-checked before being spoken, with planted false claims visibly blocked from air.
- engineer (run 1): A co-commentator that literally cannot lie: every spoken number is checked against the match ledger before it goes live, and the evidence trail is visible in Foundry traces and evals.
- engineer (run 2): What will stick is the combination of a broadcaster-grade promise, 'it can’t lie', with a concrete enforcement chain: numbers checked by code, voice audited verbatim, late cues dropped, and Foundry traces proving each decision. That is a crisp, judge-friendly story.
- ux_judge (run 1): The strongest memory hook is the trust guarantee: a live co-commentator for football that you can interrupt, in multiple languages, where every spoken number is verified before it leaves the system, and planted lies are visibly blocked by code.
- ux_judge (run 2): What will stick is the 'can't lie' angle: every spoken number is code-checked before air, and the demo proves it by rejecting a planted false stat in real time while still speaking naturally in the fan's language.

## Top-3 reasoning

- foundry_pm (run 1, high): This is one of the stronger submissions for this category because Foundry is clearly essential to the product, not ornamental. The evals, traces, voice auditing, and MCP integration are credible and well documented. Unless the live demo stumbles, it has a real shot at top 3.
- foundry_pm (run 2, high): This looks like a finalist-level Best Use of Microsoft Foundry entry. It has a coherent product story, visible Foundry dependency, real evals/traces, and a strong demo narrative. The main risk is execution polish in the final submission, not the underlying concept or technical depth.
- broadcast_lead (run 1, high): This has the strongest combination of Foundry relevance, multi-agent structure, and real broadcast trust value. The main reason it might miss top 3 is presentation compression: if the 2-minute video doesn’t communicate the value cleanly, the sophistication could be underappreciated. But on paper, it is a top-tier entrant.
- broadcast_lead (run 2, high): This looks like a top-tier category fit with strong end-to-end execution, compelling trust differentiation, and unusually good evaluation evidence. The main risk is demo clarity and whether judges can quickly grasp the production value, but on balance it feels very competitive for top 3 in this track.
- engineer (run 1, high): This is a top-tier category fit with unusually strong engineering evidence and a compelling demo story. The main thing holding it back from near-certain top 3 status is execution risk in a live judge setting, not concept or architecture.
- engineer (run 2, high): This has a credible shot at Top 3 because it is tightly aligned to the category, technically ambitious, and backed by unusually specific evidence: traces, evals, latency numbers, offline fallback, and a clear demo script. The main competition risk is that judges may prefer a simpler but more bulletproof demo, but among Foundry-focused entries this is very competitive.
- ux_judge (run 1, high): This looks top-tier for the category because it combines a strong product story, real multi-agent architecture, and unusually good verification/evaluation evidence. The main risk is demo compression, not concept or implementation. If the video clearly shows the fact-check rejection, barge-in, and Foundry traces, it absolutely has a credible Top 3 path.
- ux_judge (run 2, high): This looks like a serious contender. It combines a clear audience need, visible Foundry usage, multi-agent orchestration, eval evidence, and a polished demo plan. If the video executes cleanly, it could absolutely land top 3 in category or overall; the main challenge is presentation clarity, not substance.

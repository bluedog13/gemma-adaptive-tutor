# MAP Accelerator

*Turns MAP scores into personalized next-step instruction for advanced learners — automatically, affordably, and privately.*

## The Problem

Over 13 million students across 140+ countries take the MAP (Measures of Academic Progress) assessment by NWEA each year. MAP is computer-adaptive — it adjusts question difficulty in real-time until it finds the level where a student answers correctly about 50% of the time. That becomes their RIT score, a grade-independent measure of what they know and what they're ready to learn next.

MAP is excellent at identifying advanced learners. What remains poorly addressed in most classrooms and existing MAP workflows is what to *do* with that information.

When a student scores in the 90th+ percentile, they're flagged as "ahead." Teachers — rightly — prioritize students who need to catch up. The advanced student receives no new material at their level. When MAP tests again months later, it asks about concepts never taught. The student's percentile drops. Peers close the gap. Next year, the cycle repeats.

We observed this pattern across three consecutive years of MAP data for one student, consistent across all three subjects (Math, Reading, Science): 98th percentile entering Kindergarten, declining to the 73rd by spring — not from regression, but from stagnation. The same sawtooth pattern repeated in 1st and 2nd grade. While this is one illustrative case, the underlying dynamic — advanced students receiving no differentiated instruction — is widely documented in gifted education research and familiar to any teacher who has managed a mixed-ability classroom.

This isn't a teacher problem. It's a tooling problem. NWEA provides a Learning Continuum with a Reinforce/Develop/Introduce framework organized in 10-RIT bands. But translating that into actionable enrichment for individual students takes hours. There is no widely adopted tool in typical MAP workflows that reads a student's RIT score and automatically generates targeted "Introduce" band activities.

## The Solution

MAP Accelerator is a Gemma 4-powered enrichment copilot for teachers and parents. It ingests MAP scores, maps them to next-ready skills using NWEA's Learning Continuum, and produces personalized practice and reports — turning assessment data into instruction.

**Today, it does three things:**

1. **Ingests MAP data** — via photograph of a scorecard (multimodal vision) or manual entry
2. **Identifies what's next** — maps the student's RIT to their Introduce band and surfaces specific skills they're ready for but haven't been taught
3. **Generates enrichment** — produces targeted exercises, tracks mastery, and creates teacher/parent reports with recommended next steps

The core flow: *ingest MAP data → map to next-ready skills → generate practice → track mastery → produce reports.*

**Tomorrow**, this becomes a fully adaptive personal tutor — including offline, on-device delivery via Gemma 4's edge models, so any family can use it without cloud dependencies or privacy concerns.

## Why Gemma 4

Each capability maps to a specific need:

- **Native function calling** orchestrates the agent's tools (score analysis, curriculum lookup, exercise generation, progress tracking) based on context, not hardcoded logic
- **Multimodal vision** lets parents photograph a MAP scorecard instead of transcribing numbers
- **Structured JSON output** via constrained decoding ensures reliable, parseable data for dashboards and reports
- **Transparent stepwise explanations** help the agent show its reasoning when explaining concepts to students — supporting learning, not just answer-giving
- **128K context window** processes a student's full MAP history alongside curriculum data in a single pass
- **140+ language support** makes this accessible to multilingual families without a separate translation layer
- **Edge-ready architecture** — we built and tested with the E4B model running locally via Ollama, proving this works on a laptop today and on a phone tomorrow

## Challenges

**RIT-to-Curriculum Mapping:** NWEA's Learning Continuum data lives inside the MAP platform and isn't programmatically accessible. We built a retrieval layer over NWEA's published learning continuum documents so Gemma 4 can automatically identify Introduce-band skills for any student and generate aligned exercises.

**Calibrating Difficulty:** Advanced students need challenge, not hand-holding. We target the zone of proximal development — hard enough to stretch, structured enough not to frustrate — and ground all generated exercises in curriculum-aligned standards rather than free-form generation.

## Impact

With 13+ million students taking MAP annually, even a modest share of advanced learners who are under-challenged represents an enormous addressable need. MAP Accelerator works across Math, Reading, and Science — all three MAP subjects — and across K-12, following the NWEA learning continuum.

It is privacy-first: student data never leaves the device. It is open: built entirely on Apache 2.0 licensed Gemma 4, deployable by any school or family.

MAP already tells us which students are ready for more. MAP Accelerator makes sure they actually get it.

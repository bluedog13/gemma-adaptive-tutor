# MAP Accelerator — Gemma 4 Good Hackathon

## Competition

- **Track:** Future of Education
- **Deadline:** May 18, 2026
- **Prize Pool:** $200K
- **Platform:** Kaggle

---

## The Problem

Advanced students plateau in school — not because they stop learning, but because the system stops challenging them.

MAP (Measure of Academic Progress) by NWEA is an adaptive test used in thousands of schools. When a student scores high, they are identified as "ahead." But being ahead means:

1. The teacher focuses on students who need to catch up (rightfully so)
2. The advanced student receives no new material at their level
3. MAP is adaptive — it tests concepts NOT yet taught in class
4. The student's percentile drops as peers catch up
5. Next school year resets the cycle

**Real example (anonymized):**

- Kindergarten Fall: 98-99th percentile in Math
- Kindergarten Spring: drops to 73-81st percentile
- 1st Grade Fall: resets to 90-94th percentile
- 1st Grade Winter: drops to 83-89th percentile
- 2nd Grade Fall: 86-90th percentile
- 2nd Grade Winter: drops to 77-83rd percentile

The student's absolute scores keep growing, but the system erodes their advantage every single year. The student isn't failing — the system is failing the student.

Teachers aren't at fault — they often don't know WHAT to teach an advanced student next, and MAP data doesn't come with a lesson plan.

---

## The Solution: MAP Accelerator

A Gemma 4-powered agent that reads a student's MAP scores, identifies the next band of concepts they're ready for, and generates personalized learning challenges — so no student is left waiting for the classroom to catch up.

### How It Works

```_
Student MAP Score (e.g., RIT 196, Math, Grade 2)
         |
         v
Gemma 4 Agent analyzes using NWEA's Reinforce/Develop/Introduce framework:
  - Reinforce band (10-RIT below score) — mastered skills
  - Develop band (at score) — currently working on
  - Introduce band (10-RIT above score) — ready for next
  - Specific skill gaps to target in the Introduce band
         |
         v
Generates personalized learning path:
  - Targeted exercises at the RIGHT difficulty
  - Visual/multimodal problems (math diagrams, reading passages)
  - Adaptive difficulty based on student responses
         |
         v
Tracks progress and prepares student for next MAP test
Also generates teacher-facing reports with enrichment recommendations
```

### Why Gemma 4

| Feature | How We Use It |
|---------|---------------|
| Native function calling | Multi-tool agent: curriculum lookup, exercise generator, progress tracker |
| Multimodal input | Student can photograph their MAP scorecard → agent reads it |
| Structured JSON output | Clean analytics, progress data, teacher reports |
| Extended thinking | Walk through problem-solving steps, explain concepts |
| 128K context window | Process full MAP history + curriculum data in one pass |
| 140+ languages | Works for multilingual students worldwide |
| Edge deployment (future) | E4B can run on family's device — privacy-safe, offline |

---

## Tech Stack

```
Backend:     Python + FastAPI
Model:       Gemma 4 E4B (via Ollama, Q4_K_M quantization)
Frontend:    Gradio or Streamlit (pure Python, fast prototyping)
Database:    SQLite (student progress tracking)
Hosting:     Hugging Face Spaces / Google Cloud / Kaggle
```

---

## Agent Architecture

### Tools (Function Calling)

1. **MAP Score Analyzer** — Parse RIT scores, map to learning continuum
2. **Curriculum Lookup** — Find next-band concepts for a given RIT/subject/grade
3. **Exercise Generator** — Create problems at the target difficulty level
4. **Progress Tracker** — Log student responses, update mastery levels
5. **Teacher Report Generator** — Summarize gaps, recommend enrichment activities

### Data Flow

```_
[MAP Scorecard] --> [Score Ingestion (multimodal/manual)]
                          |
                          v
                 [MAP RIT Learning Continuum]
                          |
                          v
              [Gap Analyzer (Gemma 4 reasoning)]
                          |
                    +-----+-----+
                    |           |
                    v           v
          [Student Path]   [Teacher Report]
                    |
                    v
          [Exercise Generator]
                    |
                    v
          [Adaptive Practice Session]
                    |
                    v
          [Progress Tracker] --> feeds back to Gap Analyzer
```

---

## Submission Deliverables

| # | Deliverable | Status | Notes |
|---|------------|--------|-------|
| A | Kaggle Writeup | DRAFT | ≤1,500 words, in docs/story/writeup-draft.md |
| B | YouTube Video | TODO | ≤3 min, script in docs/story/narrative.md |
| C | Public Code Repo | IN PROGRESS | GitHub, well-documented |
| D | Live Demo | TODO | Public URL, no login/paywall |
| E | Cover Image | TODO | Required for Media Gallery |

---

## Technical Requirements Checklist

- [ ] Gemma 4 model usage — clearly demonstrated
- [ ] Post-training / domain adaptation / agentic retrieval
- [ ] Function calling — multi-tool agent
- [ ] Grounded, accurate outputs
- [ ] Architecture explanation
- [ ] Functional live demo
- [ ] Real-world utility demonstrated

---

## Timeline

### Scope: Math only (grades 2–5), bands 131–220. Option to enter past exam scores.

| Week | Dates | Focus |
|------|-------|-------|
| 1 | Apr 3–10 | Story, architecture design, set up Gemma 4 locally ✅ |
| 2 | Apr 10–17 | Core agent: MAP ingestion + gap analysis + exercise generation |
| 3 | Apr 17–24 | Function calling tools, progress tracking, frontend |
| 4 | Apr 24–May 1 | Domain adaptation (RAG/fine-tuning), polish UI |
| 5 | May 1–10 | Testing, live demo deployment, write Kaggle writeup |
| 6 | May 10–18 | Record video, final polish, submit |

---

## Key Differentiators

1. **Solves a real, documented problem** — with actual MAP data showing the pattern
2. **Serves BOTH student and teacher** — not just another chatbot
3. **Multi-tool agent** — function calling, not just prompting
4. **Privacy-first** — can run on-device with E4B (future roadmap)
5. **Universal** — works for any student, any school, Math/Reading/Science

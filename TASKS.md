# MAP Accelerator — Build Tasks

## Week 1: Story, Architecture, Data ✅

- [x] Problem narrative and writeup draft
- [x] Video script
- [x] Project plan and architecture
- [x] Set up repo, pyproject.toml, dependencies
- [x] Gemma 4 E4B running locally via Ollama
- [x] RIT-to-concept data — Math 2+ bands 131–220

## Week 2: Core App

### Data Models & Database
- [ ] Pydantic schemas — Student, Score, Exercise, SessionResult
- [ ] SQLite database setup with SQLAlchemy
- [ ] Tables: students, scores, sessions, exercise_results

### Score Input
- [ ] API endpoint to accept student info + RIT scores (1–3 scores: Fall/Winter/Spring)
- [ ] Validate RIT score is within range (100–350)
- [ ] Store scores in database

### Curriculum Mapper
- [ ] Load RIT-to-concept JSON
- [ ] Given a RIT score, return Develop band (current) and Introduce band (next)
- [ ] If 2+ scores provided, detect trend (growing / stalling / declining)

### Exercise Generator
- [ ] Prompt Gemma 4 with Introduce band concepts
- [ ] Generate varied question types (word problems, multiple choice, fill-in-the-blank)
- [ ] Adjust focus based on weak concepts from prior sessions
- [ ] Return structured JSON (question, choices, answer, explanation)

### Practice Session
- [ ] API endpoint to start a session (student + target concepts)
- [ ] Serve questions one at a time
- [ ] Accept answers, score correct/incorrect
- [ ] Track per-concept mastery (e.g., 3/5 correct)
- [ ] End session and store results in database

### Progress & Reports
- [ ] API endpoint to get student progress (concept mastery over time)
- [ ] Generate teacher/parent report via Gemma 4 (summary + recommendations)

## Week 3: Frontend & Function Calling

- [ ] Gradio UI — score entry form
- [ ] Gradio UI — practice session (question display, answer input, feedback)
- [ ] Gradio UI — progress dashboard and report view
- [ ] Gemma 4 function calling — wire tools (curriculum lookup, exercise gen, progress tracker)

## Week 4: Polish & Adapt

- [ ] Tune prompts for exercise quality and age-appropriate language
- [ ] Add difficulty scaling within concepts
- [ ] Error handling and edge cases
- [ ] UI polish

## Week 5: Deploy & Write

- [ ] Deploy live demo (Hugging Face Spaces / Google Cloud)
- [ ] Finalize Kaggle writeup
- [ ] Test end-to-end flow

## Week 6: Video & Submit

- [ ] Record 3-min YouTube video
- [ ] Create cover image
- [ ] Final submission on Kaggle

# Backlog

Future enhancements and ideas captured during development.

## Adaptive Practice Improvements

- **Progressive difficulty within concepts** — As a student masters a concept (e.g., 80%+ across sessions), generate harder questions for that concept rather than repeating the same difficulty level.
- **Automatic band progression** — When a student consistently scores high across all concepts in their current Introduce band, suggest or automatically move them to the next RIT band without requiring a new MAP test score.
- **Per-concept mastery trend** — Track and visualize how each concept's accuracy changes over time (e.g., "Fractions: 40% → 60% → 85% across 3 sessions"). Currently the Report tab shows aggregate stats but not per-concept trends.

## MAP-Style UI Enhancements

- **Multi-select checkbox questions** ("Choose two") — Needs `gr.CheckboxGroup` with square checkbox CSS.
- **Drag-and-drop interactions** (ordering, matching) — Not natively supported in Gradio.
- **Image-based answer choices** — Needs custom HTML rendering.
- **Two-column Part A / Part B layout** — Needs CSS grid within HTML component.
- **Passage display with numbered paragraphs** — Needs HTML rendering for reading passages.
- **Text highlight/selection in passages** — Needs JavaScript interaction.

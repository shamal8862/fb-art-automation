# Batch 05

Completed under queue/not-approved:
- ANY__character-study__professor-x__b05-05: one image.
- WINDOW-2026-11-06_to_2026-11-08__film-release__ramayana-france__b05-06: 01 Rama, 02 Sita, 03 Ravana. Same 1122x1402 pixel dimensions, ordered carousel. Traditional-epic interpretations, not actor likenesses. Release information is territory-specific to France.
- ON-2026-11-07__anniversary-tribute__leonard-cohen__b05-07: symbolic tribute for tenth death anniversary; November 7, not announcement date November 10. No lyrics quoted.

Incomplete briefs in drafts/batch-05-incomplete: Spider-Man (two rejected generation attempts) and Batman (one rejected attempt). No final images exist; not placed in queue/not-approved. The image tool reported moderation_blocked category other; no more specific reason supplied. CLI/API fallback exists but requires explicit user choice and OPENAI_API_KEY; not invoked.

Timing inspection: new code parses dates/windows and calls get_slot_for_package. It currently operates on UTC calendar dates, not publish_timezone. Exact-day fallback can return an occupied or passed noon slot; exhausted windows fall back to ordinary rotation outside window. No scheduler changes or live API runs performed. All completed packages require manual approval.

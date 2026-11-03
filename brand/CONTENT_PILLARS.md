# Doodlore content pillars and dated packages

## Coverage
Rotate subjects across a batch; avoid runs of only family sketches or humanitarian suffering.
Suggested starting mix (editorial, not scheduler logic): 35% human stories and humour; 25% film/comic characters; 15% music/actor tributes; 15% culture and mythology; 10% news/humanitarian.
Adjust with actual audience response.

Pillars:
- human_stories: friendship, everyday emotion, humour, animals and ordinary life.
- character_study: Spider-Man, Batman, Professor X and other recognizable fictional characters, with verified facts.
- film_release: upcoming/recent cinema; verify title, release market/date and official visual references.
- epic_culture: Rama, Sita, Ravana and other cultural subjects. Distinguish traditional epic interpretation from a specific film adaptation; explain regional/traditional variation respectfully.
- anniversary_tribute: deceased musicians, actors and other notable people; verify identity, death status and exact anniversary date.
- birthday_tribute: birthday observances, clearly distinguish living and deceased people.
- humanitarian_news: verified civilian-focused context, dignified symbolic scenes, no invented eyewitness claims.

## Research and caption standards
One emotional/art observation plus 1-3 accurate interesting facts, then an optional relevant question and exactly five hashtags. No AI disclosure line in captions (user adds platform label); keep internal ai_generated=true.
Use official studio/publisher/artist estate/museum/archive sources when available and save URLs. Facts should add meaning, not become trivia padding.
Name continuity/version: comics, film title/year, universe or adaptation. A death or near-death scene is fiction; do not imply the actor died. Spoiler warning before plot details. Avoid claiming a living performer is deceased; no memorial imagery solely because someone is elderly.
Fan art must be original composition, not copied posters; do not imply official affiliation, endorsement or guaranteed monetization rights.
For actor likeness or specific movie costume use verified image references.
Film releases vary by market; use territory-specific confirmed dates. Do not treat an unverified release date as an exact-day package.

## Folder naming — new packages
Keep each post a DIRECT child of the existing category folder. Do not add topic nesting inside evergreen/ or timely/, because the watcher expects individual post packages there.

Evergreen:
queue/not-approved/evergreen/ANY__character-study__batman-rooftop__b05-01/
queue/not-approved/evergreen/ANY__human-stories__shared-umbrella__b05-02/

Flexible timely:
queue/not-approved/timely/WINDOW-2026-11-06_to_2026-11-08__film-release__verified-title-market__b05-03/

Exact-day:
queue/not-approved/timely/ON-YYYY-MM-DD__anniversary-tribute__person-slug__b05-04/
queue/not-approved/timely/ON-YYYY-MM-DD__birthday-tribute__person-slug__b05-05/

Replace date placeholders with verified real dates. ON date means intended publication date, never generation date. Add creation date separately to metadata. These names are human-readable conventions, not implemented scheduling behaviour.

## Metadata additions
Keep type as evergreen or timely (existing watcher expects these).
Add content_pillar, subject_name, character_version, sources, verified_at, created_at, batch and ai_generated.
For exact-day content also add publish_on (YYYY-MM-DD), publish_timezone (Asia/Colombo unless explicitly chosen otherwise), strict_date=true, date_basis, and review_status=pending_manual_approval.
For flexible timely posts add publish_not_before, publish_not_after and strict_date=false.
Confirm anniversary month/day against reliable sources; compute year count only after checking both dates.

## Scheduler date enforcement (Implemented & Live)
As of November 3, 2026: The scheduler fully supports folder prefixes and metadata timing rules via `CalendarPlanner.get_slot_for_package(pkg)`:
- `ON-YYYY-MM-DD`: Schedules strictly on that exact target calendar date. If the date has already passed, strict mode prevents scheduling. Never silently rolls an anniversary or tribute to another day.
- `WINDOW-YYYY-MM-DD_to_YYYY-MM-DD`: Finds the earliest non-colliding preferred slot within the start and end dates.
- `ANY__`: Follows standard FIFO rotation queue.
- Metadata keys `publish_on`, `publish_not_before`, `publish_not_after`, `target_time_utc`, and `strict_date` are fully parsed and honored.
Once approved by moving from `queue/not-approved/` into `queue/`, the scheduler automatically assigns and guarantees the requested date and window!

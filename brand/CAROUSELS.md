# Carousel authoring standard

Use carousels when a sequence adds value: character studies, film/epic comparisons, a short visual story, or a tribute with distinct moments. Do not create repetitive slides just to increase count. Prefer 3-5 slides; keep within this engine's current 2-10 image range (Instagram client currently truncates beyond 10).

All new packages remain under queue/not-approved/evergreen or queue/not-approved/timely for manual approval. Use the topic/date folder conventions in CONTENT_PILLARS.md.

Example:
ANY__character-study__spider-man__b05-01/
  01.png
  02.png
  03.png
  caption.txt
  metadata.json
  prompt-01.txt
  prompt-02.txt
  prompt-03.txt

Use zero-padded names 01.png through 10.png. The current watcher uses case-insensitive lexical sorting, NOT natural numeric sorting; unpadded 1,2,10 sorts as 1,10,2. Do not mix naming patterns or extensions unnecessarily.

Only intended final slides belong at package root. Never put alternate renders, thumbnails, contact sheets or image-v2.png there: every supported root image becomes a slide. Keep discarded variants in drafts/archive outside the package.

All slides share actual pixel dimensions and aspect ratio, normally portrait 4:5. Verify output dimensions rather than assuming the prompt guarantees them. First slide must stand alone as a cover, since the intended story workflow uses it. Do not promise story publishing was verified merely because a carousel was generated.

One main caption, meaningful sourced facts when useful, exactly five hashtags; no caption AI disclosure line because the user applies the platform label. Retain ai_generated=true internally.
Metadata: format=carousel; slide_count; slides list with filename, alt_text, medium and subject; sources and factual verification; content_pillar; normal review/date fields. These are authoring metadata, not a promise that all fields are enforced by scheduler.

Visual continuity: same Doodlore materials and small signature, but vary framing and distance deliberately without disorienting a single sequence. No real artist hands by default. Drawing remains loose and expressive, paper/photo believable.

Review each slide's spelling, anatomy, facts and signature, then review full order for narrative flow. Approve by moving the entire folder. Exact-day folder naming remains advisory until date-aware scheduler support is verified.

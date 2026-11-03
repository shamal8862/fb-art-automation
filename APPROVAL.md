# Manual content approval

All new post packages go into queue/not-approved/evergreen or queue/not-approved/timely. The scheduler ignores these locations. A ready.flag or metadata status does not make a package here schedulable.

1. Double-click review-content.bat in the project root to open pending and approved folders.
2. Open a package and review image.png and caption.txt. Edit the caption if needed.
3. Approve by MOVING the whole package folder into queue/evergreen or queue/timely, matching its category. Use Ctrl+X then Ctrl+V to move reliably. Do not move just the image.
4. Leave unwanted packages in not-approved, or delete them manually.

Moving into a normal queue folder authorizes pickup on the next scheduler scan. This launcher does not start the scheduler. Folder placement controls approval; review_status is informational and may remain pending after a manual move. Do not store alternate renders in a package. Single posts have one image.png; carousels contain only final ordered slides named 01.png, 02.png and so on. See brand/CAROUSELS.md.

The existing tribute has been returned to not-approved/timely for your review. Moving a local package cannot cancel a post already accepted by Facebook; this operation did not contact Facebook.
-- NutriPal FAQ content
--
-- Real content for the faq_entries table (see sql/schema.sql), shown on the
-- standalone FAQ page reached from the menu's Help submenu. Distinct from
-- sql/init_lookups.sql (lookup-table vocabularies, including lut_faq_section
-- itself) and sql/sample_data.sql (illustrative fake data) - this is real,
-- hand-authored app content.
--
-- question/answer are Markdown, rendered client-side (frontend/faq.html).
-- section_id values match sql/init_lookups.sql's lut_faq_section seed
-- (3 = Heart Rate, 7 = Steps, 9 = Contact & Support).

USE nutripal;

INSERT INTO faq_entries (section_id, question, answer, display_order) VALUES
(
3,
'How are the heart-rate zones calculated?',
'NutriPal uses the classic 5-zone heart-rate training model, based on percentage of your Max Heart Rate (Max HR):

| Zone | Threshold (% of Max HR) | Label |
|---|---|---|
| 1 | 50%–60% | Very Light |
| 2 | 60%–70% | Aerobic |
| 3 | 70%–80% | Moderate |
| 4 | 80%–90% | Hard |
| 5 | 90%+ | Maximum |

A reading below 50% of Max HR is not shown with a zone badge at all.

**Formula:** `pct = bpm / maxHr`, then the highest zone whose threshold `pct` meets or exceeds is used - so each zone''s lower bound is inclusive and its upper bound is exclusive.

**Where Max HR comes from:** whichever source you have selected in Settings -

- **Age** - the classic `220 - age` estimate.
- **Observed** - the highest *sustained* heart rate seen during real running/treadmill/aerobics-type sessions over the trailing 21 days, divided by 0.95 (a hard training effort rarely reaches literal 100% of true max). "Sustained" means the highest rolling-median bpm over any 2-minute window in the session, not just the single highest raw reading - a lone sensor glitch (one reading spiking far above everything around it) is ignored, while a genuinely sustained hard effort still counts.
- **Manual** - a bpm value you enter yourself.

Whichever source is active, it is resolved *as of the specific date* being shown - not just today''s value - so an old exercise session is zone-colored against the Max HR that was actually in effect back then, not today''s.',
1
),
(
7,
'Where do my step counts come from, and why does the source say "Mixed"?',
'Two sources can report steps for the same stretch of time: your Fitbit watch, and your phone (via Health Connect or another app). Since both can report overlapping real activity, simply adding them together would double-count the same steps.

**The rule:** for every 10-minute window of the day, NutriPal trusts the Fitbit watch''s count *unless* it reported very few steps (under 100) **and** the phone reported at least 3x more for that same window. Only then is the phone''s count used instead for that window - the idea being that a gap that large means the watch genuinely wasn''t tracking (not worn, charging, or something like a shopping cart handle suppressing wrist swing), not just an ordinary difference in sensor sensitivity.

Each day''s **Source** reflects what happened across the whole day:

- **Fitbit** - the watch was trusted for every window.
- **Phone** - the watch had nothing usable all day; the phone covered the whole day instead.
- **Mixed** - some windows came from the watch, others from the phone.

A day with no readings from either source at all still counts as **0 steps** (source **None**), rather than being skipped - a missed sync shouldn''t quietly disappear from your averages instead of counting against them. This only applies through today - a day that hasn''t happened yet is never shown at all.',
1
),
(
9,
'How do I report a bug, request a feature, or get support?',
'NutriPal is built and maintained by **5K-IoT**. For bug reports, feature requests, or any other support, email:

**support@5k-iot.com**',
1
);

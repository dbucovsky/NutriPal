-- NutriPal FAQ content
--
-- Real content for the faq_entries table (see sql/schema.sql), shown on the
-- standalone FAQ page reached from the menu's Help submenu. Distinct from
-- sql/init_lookups.sql (lookup-table vocabularies) and sql/sample_data.sql
-- (illustrative fake data) - this is real, hand-authored app content.
--
-- question/answer are Markdown, rendered client-side (frontend/faq.html).

USE nutripal;

INSERT INTO faq_entries (question, answer, display_order) VALUES
(
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
);

-- NutriPal sample data
--
-- Illustrative seed data for offline/throwaway-DB review of the food-log
-- side of the schema: foods_db (the catalog) and food_log_entries (the
-- strict food_id + serving_amount reference model — see
-- doc/wiki/Database-Schema.md). 4 days of mixed and repeated meals for a
-- single user, deliberately reusing several foods across days (oatmeal
-- breakfast, salmon leftovers, chicken salad, apple) to show what real
-- repeat-logging looks like against the ratio/quantity model, plus one
-- genuine version fork (Oatmeal with Banana gets a real recipe change on
-- day 4, not just a quantity difference) and two nutripal-created entries
-- (no api_uid/data_source, matching a future custom-logging feature).
--
-- Run AFTER sql/schema.sql and sql/init_lookups.sql — this file assumes
-- every lookup it references (units, ingestion sources, meal types,
-- nutrients, the seeded 'gram' serving unit, the sentinel users/groups
-- rows) already exists and does not re-seed any of it, to avoid duplicate
-- keys when run against a real freshly-initialized database. The one
-- exception is lut_data_source, which init_lookups.sql deliberately leaves
-- empty (grows dynamically as real devices/apps are encountered) — this
-- file seeds two illustrative rows for its own use.
--
-- Does NOT cover steps/heart-rate/weight/exercise/sleep — those categories
-- are now exercised against real data via the actual importers
-- (scripts/import-health-connect.php, scripts/sync-google-health.php)
-- rather than needing static illustrative rows here.

USE nutripal;

INSERT INTO lut_data_source (id, name) VALUES
    (1, 'Fitbit App'), (2, 'Charge 5');

-- ----------------------------------------------------------------------------
-- foods_db — 10 catalog foods (mass dimension) plus one genuine version
-- fork (Oatmeal with Banana v1, id 11 — a real recipe change, not just a
-- different quantity of v0). Nutrition is per-100g, matching label
-- convention. group_id = 1 (the 'none' sentinel — these are personal
-- foods, not shared with a group); user_id = 2 (the one seeded real user).
-- ----------------------------------------------------------------------------

INSERT INTO foods_db (id, name, dimension_id, version, group_id, user_id, energy_kcal, total_protein_g, total_carbohydrate_g, total_fat_g) VALUES
    (1, 'Oatmeal with Banana', 1, NULL, 1, 2, 180.00, 5.00, 32.00, 3.50),
    (2, 'Grilled Chicken Salad', 1, NULL, 1, 2, 140.00, 18.00, 6.00, 5.00),
    (3, 'Salmon with Rice', 1, NULL, 1, 2, 165.00, 13.00, 17.00, 5.00),
    (4, 'Apple', 1, NULL, 1, 2, 52.00, 0.30, 14.00, 0.20),
    (5, 'Greek Yogurt', 1, NULL, 1, 2, 59.00, 10.00, 3.60, 0.40),
    (6, 'Turkey Sandwich', 1, NULL, 1, 2, 250.00, 14.00, 28.00, 9.00),
    (7, 'Scrambled Eggs with Toast', 1, NULL, 1, 2, 200.00, 11.00, 15.00, 11.00),
    (8, 'Pasta with Tomato Sauce', 1, NULL, 1, 2, 140.00, 5.00, 27.00, 2.00),
    (9, 'Tofu Vegetable Stir-fry', 1, NULL, 1, 2, 90.00, 7.00, 6.00, 5.00),
    (10, 'Almonds', 1, NULL, 1, 2, 579.00, 21.00, 22.00, 50.00),
    -- Version fork: same name as id 1, genuinely different recipe (less
    -- sugar, more fiber) — not a quantity difference, so this earns a new
    -- version rather than reusing id 1 (see doc/wiki/Database-Schema.md's
    -- "quantity problem" section for why that distinction matters).
    (11, 'Oatmeal with Banana', 1, 1, 1, 2, 165.00, 5.50, 28.00, 3.00);

-- ----------------------------------------------------------------------------
-- foods_db_nutrients — a representative subset per food, all per-100g.
-- Almonds (id 10) includes a hand-entered LEUCINE value: LEUCINE is kept in
-- lut_nutrient specifically as a nutrient no real source ever reports (see
-- sql/init_lookups.sql) — this is what a manually-tracked micronutrient
-- looks like now that the SRC/FIX/MOD modifier system has been replaced by
-- versioning: it's just an ordinary nutrient row, not a special case.
-- unit_id 3 = gram throughout (see sql/init_lookups.sql).
-- ----------------------------------------------------------------------------

INSERT INTO foods_db_nutrients (food_id, nutrient_id, quantity, unit_id) VALUES
    -- Oatmeal with Banana (v0)
    (1, 1, 0.040, 3), (1, 2, 0.150, 3), (1, 3, 4.00, 3), (1, 4, 8.00, 3),
    -- Grilled Chicken Salad
    (2, 1, 0.350, 3), (2, 9, 0.060, 3), (2, 2, 0.250, 3),
    -- Salmon with Rice
    (3, 1, 0.150, 3), (3, 2, 0.200, 3), (3, 9, 0.030, 3),
    -- Apple
    (4, 3, 2.40, 3), (4, 4, 10.00, 3), (4, 8, 0.0046, 3),
    -- Greek Yogurt
    (5, 1, 0.036, 3), (5, 5, 0.110, 3), (5, 2, 0.140, 3),
    -- Turkey Sandwich
    (6, 1, 0.600, 3), (6, 3, 2.00, 3),
    -- Scrambled Eggs with Toast
    (7, 9, 0.180, 3), (7, 1, 0.400, 3),
    -- Pasta with Tomato Sauce
    (8, 1, 0.300, 3), (8, 4, 5.00, 3), (8, 3, 2.50, 3),
    -- Tofu Vegetable Stir-fry
    (9, 1, 0.250, 3), (9, 6, 0.002, 3), (9, 5, 0.050, 3),
    -- Almonds — includes the hand-entered LEUCINE example
    (10, 5, 0.269, 3), (10, 6, 0.0037, 3), (10, 2, 0.733, 3), (10, 11, 1.470, 3),
    -- Oatmeal with Banana (v1) — lower sugar, higher fiber than v0
    (11, 1, 0.030, 3), (11, 3, 5.00, 3), (11, 4, 4.00, 3);

-- ----------------------------------------------------------------------------
-- foods_db_custom_units — one named real-world unit per food (all
-- is_default = TRUE, since each food only has one unit here). "Apple" ->
-- "medium" reuses the exact gram figure (166.6667g) a real Google Health
-- API sync computed for a medium apple during this project's development
-- (see doc/wiki/Data-Sync.md) rather than an invented number.
-- ----------------------------------------------------------------------------

INSERT INTO foods_db_custom_units (id, food_id, unit_name, equivalent_amount, is_default) VALUES
    (1, 1, 'bowl', 250.0000, TRUE),
    (2, 2, 'serving', 300.0000, TRUE),
    (3, 3, 'plate', 350.0000, TRUE),
    (4, 4, 'medium', 166.6667, TRUE),
    (5, 5, 'cup', 245.0000, TRUE),
    (6, 6, 'sandwich', 200.0000, TRUE),
    (7, 7, 'plate', 220.0000, TRUE),
    (8, 8, 'plate', 300.0000, TRUE),
    (9, 9, 'bowl', 300.0000, TRUE),
    (10, 10, 'handful (23 almonds)', 28.0000, TRUE),
    (11, 11, 'bowl', 220.0000, TRUE);

INSERT INTO lut_serving_unit (id, label, foods_db_custom_unit_id) VALUES
    (2, 'sample_oatmeal_v0_bowl', 1),
    (3, 'sample_chicken_salad_serving', 2),
    (4, 'sample_salmon_rice_plate', 3),
    (5, 'sample_apple_medium', 4),
    (6, 'sample_greek_yogurt_cup', 5),
    (7, 'sample_turkey_sandwich', 6),
    (8, 'sample_eggs_toast_plate', 7),
    (9, 'sample_pasta_plate', 8),
    (10, 'sample_tofu_stirfry_bowl', 9),
    (11, 'sample_almonds_handful', 10),
    (12, 'sample_oatmeal_v1_bowl', 11);

-- ----------------------------------------------------------------------------
-- food_log_entries — 4 days, mixed and repeated meals for user_id = 2.
-- serving_amount is a multiplier against the food's custom unit above (see
-- the header note on foods_db_custom_units), e.g. 1.2 plates, 0.85 plates
-- for smaller leftovers the next day. api_uid/data_source_id are NULL for
-- the two nutripal-created entries (ingestion_source_id = 4), matching the
-- future custom/repeat-meal logging feature — nothing was synced from
-- Google for those two.
-- ----------------------------------------------------------------------------

-- Day 1 (2026-09-01)
INSERT INTO food_log_entries (id, user_id, start_time, end_time, meal_type_id, food_id, serving_amount, serving_unit_id, data_source_id, ingestion_source_id, api_uid) VALUES
    (1, 2, '2026-09-01 12:00:00', '2026-09-01 12:01:00', 1, 1, 1.00, 2, 1, 1, 'gh-api-0001'),
    (2, 2, '2026-09-01 17:30:00', '2026-09-01 17:31:00', 2, 2, 1.00, 3, 1, 1, 'gh-api-0002'),
    (3, 2, '2026-09-02 00:00:00', '2026-09-02 00:01:00', 3, 3, 1.20, 4, 1, 1, 'gh-api-0003'),
    (4, 2, '2026-09-02 02:00:00', '2026-09-02 02:01:00', 4, 4, 1.00, 5, 1, 1, 'gh-api-0004');

-- Day 2 (2026-09-02) — oatmeal repeats (bigger bowl), salmon leftovers (smaller)
INSERT INTO food_log_entries (id, user_id, start_time, end_time, meal_type_id, food_id, serving_amount, serving_unit_id, data_source_id, ingestion_source_id, api_uid) VALUES
    (5, 2, '2026-09-02 12:00:00', '2026-09-02 12:01:00', 1, 1, 1.10, 2, 1, 1, 'gh-api-0005'),
    (6, 2, '2026-09-02 17:00:00', '2026-09-02 17:01:00', 2, 6, 1.00, 7, NULL, 4, NULL),
    (7, 2, '2026-09-03 00:30:00', '2026-09-03 00:31:00', 3, 3, 0.85, 4, 1, 1, 'gh-api-0007'),
    (8, 2, '2026-09-03 02:15:00', '2026-09-03 02:16:00', 4, 5, 1.00, 6, 1, 1, 'gh-api-0008');

-- Day 3 (2026-09-03) — chicken salad repeats, apple repeats
INSERT INTO food_log_entries (id, user_id, start_time, end_time, meal_type_id, food_id, serving_amount, serving_unit_id, data_source_id, ingestion_source_id, api_uid) VALUES
    (9, 2, '2026-09-03 11:30:00', '2026-09-03 11:31:00', 1, 7, 1.00, 8, NULL, 4, NULL),
    (10, 2, '2026-09-03 17:45:00', '2026-09-03 17:46:00', 2, 2, 0.95, 3, 1, 1, 'gh-api-0010'),
    (11, 2, '2026-09-04 00:00:00', '2026-09-04 00:01:00', 3, 8, 1.30, 9, 1, 1, 'gh-api-0011'),
    (12, 2, '2026-09-04 03:00:00', '2026-09-04 03:01:00', 4, 4, 1.00, 5, 1, 1, 'gh-api-0012');

-- Day 4 (2026-09-04) — oatmeal switches to the v1 recipe (version fork, not
-- a quantity change), salmon leftovers again, one more nutripal-created entry
INSERT INTO food_log_entries (id, user_id, start_time, end_time, meal_type_id, food_id, serving_amount, serving_unit_id, data_source_id, ingestion_source_id, api_uid) VALUES
    (13, 2, '2026-09-04 12:00:00', '2026-09-04 12:01:00', 1, 11, 1.00, 12, 1, 1, 'gh-api-0013'),
    (14, 2, '2026-09-04 17:30:00', '2026-09-04 17:31:00', 2, 3, 0.70, 4, 1, 1, 'gh-api-0014'),
    (15, 2, '2026-09-04 23:30:00', '2026-09-04 23:31:00', 3, 9, 1.00, 10, NULL, 4, NULL),
    (16, 2, '2026-09-05 01:30:00', '2026-09-05 01:31:00', 4, 10, 1.00, 11, 1, 1, 'gh-api-0016');

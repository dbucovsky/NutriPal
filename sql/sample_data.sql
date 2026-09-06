-- NutriPal sample data (checkpoint)
--
-- Illustrative seed data for the ONLY tables finalized so far in the
-- table-by-table schema review: food_log_entries / food_log_nutrients, plus
-- every lookup/reference table they depend on. Covers 4 days of mixed and
-- repeated meals for a single user, deliberately reusing some foods across
-- days (e.g. oatmeal breakfast, salmon leftovers) to exercise the
-- fingerprint/dedup logic and show what real usage looks like.
--
-- Does NOT cover steps/heart-rate/weight/exercise/sleep/foods_db — those
-- tables haven't had their detailed review pass yet.
--
-- Fingerprints are computed inline with SHA2()/CONCAT_WS() to match the
-- documented formula exactly (see doc/wiki/Database-Schema.md), rather than
-- being pre-computed by hand.
--
-- All tables here are main-schema tables (`nutripal`) — nothing seeds
-- `nutripal_hist` directly, since history rows only ever get written by the
-- BEFORE UPDATE triggers themselves.

USE nutripal;

-- ----------------------------------------------------------------------------
-- Lookups
-- ----------------------------------------------------------------------------

INSERT INTO lut_status (id, name, description) VALUES
    (1, 'none', 'Reserved sentinel status row'),
    (2, 'active', 'Normal active state'),
    (3, 'disabled', 'Deactivated but retained for history'),
    (4, 'left', 'Membership ended (used on link_user_group)');

INSERT INTO lut_dimension (id, name, description) VALUES
    (1, 'mass', 'Mass-based quantities, base unit gram'),
    (2, 'volume', 'Volume-based quantities, base unit milliliter');

INSERT INTO unit_conversions (id, name, dimension_id, factor_to_base) VALUES
    (1, 'milligram', 1, 0.001),
    (2, 'gram', 1, 1),
    (3, 'kilogram', 1, 1000),
    (4, 'ounce', 1, 28.3495),
    (5, 'pound', 1, 453.592),
    (6, 'milliliter', 2, 1),
    (7, 'liter', 2, 1000),
    (8, 'teaspoon', 2, 4.92892),
    (9, 'tablespoon', 2, 14.7868),
    (10, 'cup', 2, 236.588),
    (11, 'fluid_ounce', 2, 29.5735);

INSERT INTO lut_ingestion_source (id, name, description) VALUES
    (1, 'google_health_api', 'Live incremental sync from the Google Health API'),
    (2, 'google_takeout', 'Bulk historical import from a Google Takeout export'),
    (3, 'mixed', 'Structural conflict between the two sources, resolved'),
    (4, 'nutripal', 'Created directly in the app');

INSERT INTO lut_meal_type (id, name) VALUES
    (1, 'BREAKFAST'), (2, 'LUNCH'), (3, 'DINNER'), (4, 'SNACK'),
    (5, 'ANYTIME'), (6, 'BEFORE_DINNER');

INSERT INTO lut_data_source (id, name) VALUES
    (1, 'Fitbit App'), (2, 'Charge 5');

INSERT INTO lut_nutrient_value_type (id, name, description) VALUES
    (1, 'SRC', 'Raw value as imported from the source, always preserved untouched'),
    (2, 'FIX', 'Hard override; wins outright when present'),
    (3, 'MOD', 'Additive adjustment on top of SRC, positive or negative');

INSERT INTO lut_nutrient (id, name) VALUES
    (1, 'SODIUM'), (2, 'POTASSIUM'), (3, 'DIETARY_FIBER'), (4, 'SUGAR'),
    (5, 'CALCIUM'), (6, 'IRON'), (7, 'VITAMIN_A'), (8, 'VITAMIN_C'),
    (9, 'CHOLESTEROL'), (10, 'SATURATED_FAT'), (11, 'LEUCINE');

INSERT INTO lut_serving_unit (id, label, unit_conversion_id) VALUES
    (1, 'gram', 2),
    (2, 'cup', 10),
    (3, 'tablespoon', 9),
    (4, 'ounce', 4);

-- ----------------------------------------------------------------------------
-- Users / groups — sentinel rows plus the one real seeded user
-- ----------------------------------------------------------------------------

INSERT INTO users (id, email, name, status_id) VALUES
    (1, NULL, 'system', 1),
    (2, 'damian.bucovsky@gmail.com', 'Damian', 2);

INSERT INTO groups (id, name, status_id) VALUES
    (1, 'none', 1);

-- ----------------------------------------------------------------------------
-- Food log — 4 days, mixed and repeated meals for user_id = 2
-- ----------------------------------------------------------------------------

-- Day 1 (2026-09-01)

INSERT INTO food_log_entries
    (id, user_id, start_time, end_time, brand_name, food_name, meal_type_id, energy_kcal, is_energy_estimated, total_protein_g, total_carbohydrate_g, total_fat_g, serving_amount, serving_unit_id, data_source_id, ingestion_source_id, api_uid, fingerprint)
VALUES
    (1, 2, '2026-09-01 12:00:00', '2026-09-01 12:01:00', NULL, 'Oatmeal with Banana', 1, 320.00, FALSE, 10.00, 58.00, 6.00, 1.5, 2, 1, 1, 'gh-api-0001',
        SHA2(CONCAT_WS('|', '2026-09-01 12:00:00', '2026-09-01 12:01:00', 'oatmeal with banana', 'breakfast', ''), 256)),
    (2, 2, '2026-09-01 17:30:00', '2026-09-01 17:31:00', NULL, 'Grilled Chicken Salad', 2, 410.00, FALSE, 38.00, 20.00, 18.00, 1, 2, 1, 1, 'gh-api-0002',
        SHA2(CONCAT_WS('|', '2026-09-01 17:30:00', '2026-09-01 17:31:00', 'grilled chicken salad', 'lunch', ''), 256)),
    (3, 2, '2026-09-02 00:00:00', '2026-09-02 00:01:00', NULL, 'Salmon with Rice', 3, 560.00, FALSE, 42.00, 55.00, 16.00, 8, 4, 1, 1, 'gh-api-0003',
        SHA2(CONCAT_WS('|', '2026-09-02 00:00:00', '2026-09-02 00:01:00', 'salmon with rice', 'dinner', ''), 256)),
    (4, 2, '2026-09-02 02:00:00', '2026-09-02 02:01:00', NULL, 'Apple', 4, 95.00, FALSE, 0.50, 25.00, 0.30, 1, 1, 1, 1, 'gh-api-0004',
        SHA2(CONCAT_WS('|', '2026-09-02 02:00:00', '2026-09-02 02:01:00', 'apple', 'snack', ''), 256));

-- Day 2 (2026-09-02) — oatmeal breakfast repeats (slightly bigger portion), salmon leftovers repeat

INSERT INTO food_log_entries
    (id, user_id, start_time, end_time, brand_name, food_name, meal_type_id, energy_kcal, is_energy_estimated, total_protein_g, total_carbohydrate_g, total_fat_g, serving_amount, serving_unit_id, data_source_id, ingestion_source_id, api_uid, fingerprint)
VALUES
    (5, 2, '2026-09-02 12:00:00', '2026-09-02 12:01:00', NULL, 'Oatmeal with Banana', 1, 340.00, FALSE, 11.00, 61.00, 6.50, 1.75, 2, 1, 1, 'gh-api-0005',
        SHA2(CONCAT_WS('|', '2026-09-02 12:00:00', '2026-09-02 12:01:00', 'oatmeal with banana', 'breakfast', ''), 256)),
    (6, 2, '2026-09-02 17:00:00', '2026-09-02 17:01:00', 'Generic', 'Turkey Sandwich', 2, 450.00, FALSE, 28.00, 45.00, 15.00, 1, 1, NULL, 4, NULL,
        SHA2(CONCAT_WS('|', '2026-09-02 17:00:00', '2026-09-02 17:01:00', 'turkey sandwich', 'lunch', 'generic'), 256)),
    (7, 2, '2026-09-03 00:30:00', '2026-09-03 00:31:00', NULL, 'Salmon with Rice', 3, 520.00, FALSE, 40.00, 50.00, 15.00, 7, 4, 1, 1, 'gh-api-0007',
        SHA2(CONCAT_WS('|', '2026-09-03 00:30:00', '2026-09-03 00:31:00', 'salmon with rice', 'dinner', ''), 256)),
    (8, 2, '2026-09-03 02:15:00', '2026-09-03 02:16:00', NULL, 'Greek Yogurt', 4, 130.00, FALSE, 15.00, 9.00, 4.00, 1, 2, 1, 1, 'gh-api-0008',
        SHA2(CONCAT_WS('|', '2026-09-03 02:15:00', '2026-09-03 02:16:00', 'greek yogurt', 'snack', ''), 256));

-- Day 3 (2026-09-03) — chicken salad repeats

INSERT INTO food_log_entries
    (id, user_id, start_time, end_time, brand_name, food_name, meal_type_id, energy_kcal, is_energy_estimated, total_protein_g, total_carbohydrate_g, total_fat_g, serving_amount, serving_unit_id, data_source_id, ingestion_source_id, api_uid, fingerprint)
VALUES
    (9, 2, '2026-09-03 11:30:00', '2026-09-03 11:31:00', NULL, 'Scrambled Eggs with Toast', 1, 360.00, FALSE, 20.00, 30.00, 17.00, 1, 1, NULL, 4, NULL,
        SHA2(CONCAT_WS('|', '2026-09-03 11:30:00', '2026-09-03 11:31:00', 'scrambled eggs with toast', 'breakfast', ''), 256)),
    (10, 2, '2026-09-03 17:45:00', '2026-09-03 17:46:00', NULL, 'Grilled Chicken Salad', 2, 400.00, FALSE, 37.00, 19.00, 17.00, 1, 2, 1, 1, 'gh-api-0010',
        SHA2(CONCAT_WS('|', '2026-09-03 17:45:00', '2026-09-03 17:46:00', 'grilled chicken salad', 'lunch', ''), 256)),
    (11, 2, '2026-09-04 00:00:00', '2026-09-04 00:01:00', NULL, 'Pasta with Tomato Sauce', 3, 480.00, FALSE, 15.00, 78.00, 12.00, 2, 1, 1, 1, 'gh-api-0011',
        SHA2(CONCAT_WS('|', '2026-09-04 00:00:00', '2026-09-04 00:01:00', 'pasta with tomato sauce', 'dinner', ''), 256)),
    (12, 2, '2026-09-04 03:00:00', '2026-09-04 03:01:00', NULL, 'Apple', 4, 95.00, FALSE, 0.50, 25.00, 0.30, 1, 1, 1, 1, 'gh-api-0012',
        SHA2(CONCAT_WS('|', '2026-09-04 03:00:00', '2026-09-04 03:01:00', 'apple', 'snack', ''), 256));

-- Day 4 (2026-09-04) — oatmeal and salmon repeat again, demonstrating a
-- nutripal-created entry (id 15) with no api_uid/data_source

INSERT INTO food_log_entries
    (id, user_id, start_time, end_time, brand_name, food_name, meal_type_id, energy_kcal, is_energy_estimated, total_protein_g, total_carbohydrate_g, total_fat_g, serving_amount, serving_unit_id, data_source_id, ingestion_source_id, api_uid, fingerprint)
VALUES
    (13, 2, '2026-09-04 12:00:00', '2026-09-04 12:01:00', NULL, 'Oatmeal with Banana', 1, 330.00, FALSE, 10.50, 59.00, 6.20, 1.6, 2, 1, 1, 'gh-api-0013',
        SHA2(CONCAT_WS('|', '2026-09-04 12:00:00', '2026-09-04 12:01:00', 'oatmeal with banana', 'breakfast', ''), 256)),
    (14, 2, '2026-09-04 17:30:00', '2026-09-04 17:31:00', NULL, 'Salmon with Rice', 2, 540.00, FALSE, 41.00, 52.00, 15.50, 7.5, 4, 1, 1, 'gh-api-0014',
        SHA2(CONCAT_WS('|', '2026-09-04 17:30:00', '2026-09-04 17:31:00', 'salmon with rice', 'lunch', ''), 256)),
    (15, 2, '2026-09-04 23:30:00', '2026-09-04 23:31:00', NULL, 'Tofu Vegetable Stir-fry', 3, 380.00, TRUE, 22.00, 30.00, 18.00, 1, 1, NULL, 4, NULL,
        SHA2(CONCAT_WS('|', '2026-09-04 23:30:00', '2026-09-04 23:31:00', 'tofu vegetable stir-fry', 'dinner', ''), 256)),
    (16, 2, '2026-09-05 01:30:00', '2026-09-05 01:31:00', NULL, 'Almonds', 4, 170.00, FALSE, 6.00, 6.00, 15.00, 1, 4, 1, 1, 'gh-api-0016',
        SHA2(CONCAT_WS('|', '2026-09-05 01:30:00', '2026-09-05 01:31:00', 'almonds', 'snack', ''), 256));

-- ----------------------------------------------------------------------------
-- Nutrient breakdown — a representative subset per entry (SRC rows), plus
-- one MOD example (Leucine, never reported by the source) and one FIX
-- example (a corrected sodium value), demonstrating the effective-value
-- mechanism: FIX wins outright; otherwise GREATEST(0, SRC + MOD).
-- ----------------------------------------------------------------------------

INSERT INTO food_log_nutrients (user_id, food_log_entry_id, nutrient_id, quantity, unit_id, value_type_id) VALUES
    -- Entry 1: Oatmeal with Banana (day 1)
    (2, 1, 1, 95.0, 1, 1), (2, 1, 2, 380.0, 1, 1), (2, 1, 3, 8.0, 2, 1), (2, 1, 4, 18.0, 2, 1),
    -- Entry 2: Grilled Chicken Salad
    (2, 2, 1, 420.0, 1, 1), (2, 2, 2, 610.0, 1, 1), (2, 2, 9, 85.0, 1, 1),
    -- Entry 3: Salmon with Rice (day 1 dinner) — includes a Leucine MOD (never reported by the source)
    (2, 3, 1, 310.0, 1, 1), (2, 3, 5, 40.0, 1, 1), (2, 3, 11, 2800.0, 1, 3),
    -- Entry 4: Apple
    (2, 4, 3, 4.0, 2, 1), (2, 4, 4, 19.0, 2, 1), (2, 4, 8, 8.4, 1, 1),
    -- Entry 5: Oatmeal with Banana (day 2, repeat) — a corrected sodium FIX
    (2, 5, 1, 90.0, 1, 1), (2, 5, 1, 100.0, 1, 2), (2, 5, 2, 400.0, 1, 1),
    -- Entry 6: Turkey Sandwich
    (2, 6, 1, 780.0, 1, 1), (2, 6, 3, 4.0, 2, 1),
    -- Entry 7: Salmon with Rice (day 2, leftovers)
    (2, 7, 1, 300.0, 1, 1), (2, 7, 5, 38.0, 1, 1),
    -- Entry 8: Greek Yogurt
    (2, 8, 1, 60.0, 1, 1), (2, 8, 5, 150.0, 1, 1), (2, 8, 4, 8.0, 2, 1),
    -- Entry 9: Scrambled Eggs with Toast
    (2, 9, 1, 480.0, 1, 1), (2, 9, 9, 370.0, 1, 1),
    -- Entry 10: Grilled Chicken Salad (repeat)
    (2, 10, 1, 410.0, 1, 1), (2, 10, 2, 600.0, 1, 1),
    -- Entry 11: Pasta with Tomato Sauce
    (2, 11, 1, 620.0, 1, 1), (2, 11, 3, 6.0, 2, 1), (2, 11, 4, 10.0, 2, 1),
    -- Entry 12: Apple (repeat)
    (2, 12, 3, 4.0, 2, 1), (2, 12, 4, 19.0, 2, 1),
    -- Entry 13: Oatmeal with Banana (day 4, repeat)
    (2, 13, 1, 92.0, 1, 1), (2, 13, 2, 390.0, 1, 1),
    -- Entry 14: Salmon with Rice (day 4, more leftovers)
    (2, 14, 1, 305.0, 1, 1), (2, 14, 5, 39.0, 1, 1),
    -- Entry 15: Tofu Vegetable Stir-fry (nutripal-created, is_energy_estimated)
    (2, 15, 1, 450.0, 1, 1), (2, 15, 3, 5.0, 2, 1),
    -- Entry 16: Almonds
    (2, 16, 5, 76.0, 1, 1), (2, 16, 6, 1.1, 1, 1);

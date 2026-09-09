<?php

declare(strict_types=1);

// Imports an Android Health Connect export (a single SQLite database) into
// the post-Takeout-redesign NutriPal schema. Real, logged, end-to-end test
// of: the strict food_log_entries -> foods_db reference model, tolerance-
// based foods_db version matching, and every other category HC now covers
// (steps, heart rate, HRV, weight/height, sleep sessions/stages, exercise).
//
// Known, disclosed simplifications (not silent gaps):
//   - HC's nutrition_record rows carry no serving/quantity field at all —
//     the reported macros ARE "however much was eaten" with no separate
//     mass. Modeled via a per-food CUSTOM UNIT ("reported serving") rather
//     than assumed grams: findOrCreateFood() ratio-matches an incoming
//     reading against every existing foods_db version sharing its name, and
//     if the implied scale factor is consistent across macros, reuses that
//     food_id with serving_amount = the derived ratio. Only forks a new
//     version when no existing version's ratios line up. See the comment
//     above findOrCreateFood() for the full rationale.
//   - exercise_session_record_table has no calories/distance/steps/average
//     heart rate columns (HC stores those in separate generic time-series
//     tables with no FK back to the session) — not cross-referenced here;
//     those four columns are left NULL for HC-sourced exercise sessions.
//   - resting_heart_rate_record_table is not imported this pass.
//   - GPS route points (exercise_route_table) are not imported; only the
//     has_gps flag is captured.
//
// Usage: php scripts/import-health-connect.php <path-to-health-connect.db>

require __DIR__ . '/../src/Env.php';
require __DIR__ . '/../src/Database.php';

Env::load(__DIR__ . '/../.env');

$hcPath = $argv[1] ?? null;
if ($hcPath === null || !is_file($hcPath)) {
    fwrite(STDERR, "Usage: php import-health-connect.php <path-to-health-connect.db>\n");
    exit(1);
}

$logDir = __DIR__ . '/../storage/import-logs';
if (!is_dir($logDir)) {
    mkdir($logDir, 0777, true);
}
$logPath = $logDir . '/health-connect-import-' . date('Ymd-His') . '.log';
$logFile = fopen($logPath, 'w');

$runStats = [];
$startedAt = microtime(true);

function logLine(string $message): void
{
    global $logFile;
    $line = '[' . date('Y-m-d H:i:s') . '] ' . $message;
    echo $line . "\n";
    fwrite($logFile, $line . "\n");
}

function bumpStat(string $category, string $key, int $by = 1): void
{
    global $runStats;
    $runStats[$category][$key] = ($runStats[$category][$key] ?? 0) + $by;
}

logLine("=== NutriPal Health Connect import starting ===");
logLine("HC db: {$hcPath}");
logLine("Log: {$logPath}");

$hc = new PDO('sqlite:' . $hcPath);
$hc->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
$pdo = Database::connect();
logLine("Connected to HC SQLite db and MySQL database " . Env::get('DB_NAME'));

$userId = 2;

// ----------------------------------------------------------------------------
// Lookup caches
// ----------------------------------------------------------------------------

function loadLookup(PDO $pdo, string $table, string $column = 'name'): array
{
    $map = [];
    foreach ($pdo->query("SELECT id, {$column} FROM {$table}") as $row) {
        $map[$row[$column]] = (int) $row['id'];
    }
    return $map;
}

$mealTypeIds = loadLookup($pdo, 'lut_meal_type');
$nutrientIds = loadLookup($pdo, 'lut_nutrient');
$unitIds = loadLookup($pdo, 'unit_conversions');
$sleepStageTypeIds = loadLookup($pdo, 'lut_sleep_stage_type');
$sleepTypeIds = loadLookup($pdo, 'lut_sleep_type');
$recordingMethodIds = loadLookup($pdo, 'lut_recording_method');
$measurementTypeIds = loadLookup($pdo, 'lut_measurement_type');
$dataSourceIds = loadLookup($pdo, 'lut_data_source');
$activityTypeIds = loadLookup($pdo, 'lut_activity_type');
$ingestionSourceHC = (int) $pdo->query("SELECT id FROM lut_ingestion_source WHERE name='health_connect'")->fetchColumn();
$gramUnitId = $unitIds['gram'];
$mmUnitId = $unitIds['millimeter'];
$gramServingUnitId = (int) $pdo->query("SELECT id FROM lut_serving_unit WHERE label='gram'")->fetchColumn();

$insertDataSource = $pdo->prepare("INSERT INTO lut_data_source (name) VALUES (?)");
function findOrCreateDataSource(?string $name, PDO $pdo, array &$cache, PDOStatement $insertStmt): ?int
{
    if ($name === null || $name === '') {
        return null;
    }
    if (isset($cache[$name])) {
        return $cache[$name];
    }
    $insertStmt->execute([$name]);
    $id = (int) $pdo->lastInsertId();
    $cache[$name] = $id;
    return $id;
}

$insertActivityType = $pdo->prepare("INSERT INTO lut_activity_type (name) VALUES (?)");
function findOrCreateActivityType(?string $name, PDO $pdo, array &$cache, PDOStatement $insertStmt): ?int
{
    if ($name === null || $name === '') {
        return null;
    }
    if (isset($cache[$name])) {
        return $cache[$name];
    }
    $insertStmt->execute([$name]);
    $id = (int) $pdo->lastInsertId();
    $cache[$name] = $id;
    return $id;
}

// app_info_id -> app name, loaded once from HC (small table)
$appNames = [];
foreach ($hc->query("SELECT row_id, app_name FROM application_info_table") as $row) {
    $appNames[(int) $row['row_id']] = $row['app_name'];
}

logLine("Lookup caches loaded: " . count($mealTypeIds) . " meal types, " . count($nutrientIds) . " nutrients, "
    . count($sleepStageTypeIds) . " sleep stage types, " . count($appNames) . " HC apps");

// ----------------------------------------------------------------------------
// Shared helpers
// ----------------------------------------------------------------------------

function hcTimeToMysql(int $epochMillis): string
{
    return gmdate('Y-m-d H:i:s', intdiv($epochMillis, 1000));
}

function hcUuid(?string $blob): ?string
{
    return ($blob === null || $blob === '') ? null : bin2hex($blob);
}

// Android RecordingMethod: 0=UNKNOWN, 1=ACTIVELY_RECORDED, 2=AUTOMATICALLY_RECORDED, 3=MANUAL_ENTRY
function hcRecordingMethodId(int $code, array $recordingMethodIds): ?int
{
    $map = [1 => 'ACTIVELY_MEASURED', 2 => 'PASSIVELY_MEASURED', 3 => 'MANUAL'];
    return isset($map[$code]) ? ($recordingMethodIds[$map[$code]] ?? null) : null;
}

// Android MealType: 0=UNKNOWN, 1=BREAKFAST, 2=LUNCH, 3=DINNER, 4=SNACK
function hcMealTypeId(int $code, array $mealTypeIds): ?int
{
    $map = [0 => 'ANYTIME', 1 => 'BREAKFAST', 2 => 'LUNCH', 3 => 'DINNER', 4 => 'SNACK'];
    return isset($map[$code]) ? ($mealTypeIds[$map[$code]] ?? null) : null;
}

// Android SleepStageType: 0=UNKNOWN,1=AWAKE,2=SLEEPING(generic),3=OUT_OF_BED,
// 4=LIGHT,5=DEEP,6=REM,7=AWAKE_IN_BED
function hcSleepStageTypeId(int $code, array $sleepStageTypeIds): ?int
{
    $map = [1 => 'AWAKE', 2 => 'ASLEEP', 3 => 'AWAKE', 4 => 'LIGHT', 5 => 'DEEP', 6 => 'REM', 7 => 'AWAKE', 0 => 'UNSPECIFIED'];
    return isset($map[$code]) ? ($sleepStageTypeIds[$map[$code]] ?? null) : null;
}

// ----------------------------------------------------------------------------
// 1. Nutrition -> foods_db (+ foods_db_nutrients) + food_log_entries
// ----------------------------------------------------------------------------

// Nutrient columns present in nutrition_record_table, mapped to our curated
// lut_nutrient names. Excludes protein/total_carbohydrate/total_fat/energy/
// energy_from_fat — those are top-level foods_db columns or derived
// summaries, not child nutrient rows.
const HC_NUTRIENT_COLUMNS = [
    'sodium' => 'SODIUM', 'potassium' => 'POTASSIUM', 'dietary_fiber' => 'DIETARY_FIBER',
    'sugar' => 'SUGAR', 'calcium' => 'CALCIUM', 'iron' => 'IRON', 'vitamin_a' => 'VITAMIN_A',
    'vitamin_c' => 'VITAMIN_C', 'cholesterol' => 'CHOLESTEROL', 'saturated_fat' => 'SATURATED_FAT',
    'trans_fat' => 'TRANS_FAT', 'biotin' => 'BIOTIN', 'copper' => 'COPPER',
    'folic_acid' => 'FOLIC_ACID', 'iodine' => 'IODINE', 'magnesium' => 'MAGNESIUM',
    'niacin' => 'NIACIN', 'pantothenic_acid' => 'PANTOTHENIC_ACID', 'phosphorus' => 'PHOSPHORUS',
    'riboflavin' => 'RIBOFLAVIN', 'thiamin' => 'THIAMIN', 'vitamin_b12' => 'VITAMIN_B12',
    'vitamin_b6' => 'VITAMIN_B6', 'vitamin_d' => 'VITAMIN_D', 'vitamin_e' => 'VITAMIN_E',
    'zinc' => 'ZINC', 'manganese' => 'MANGANESE', 'selenium' => 'SELENIUM',
    'chloride' => 'CHLORIDE', 'molybdenum' => 'MOLYBDENUM', 'chromium' => 'CHROMIUM',
    'vitamin_k' => 'VITAMIN_K', 'caffeine' => 'CAFFEINE', 'folate' => 'FOLATE',
];

// RATIO-based match, not absolute-tolerance: Health Connect never reports
// how much was actually eaten, only absolute totals for whatever amount
// that was — so "same food, different quantity" and "different food" both
// show up as different absolute numbers, and comparing them directly (the
// original approach) can't tell those apart. Confirmed on real data:
// "Yellow Onion" produced 41 near-duplicate versions that were actually the
// same onion at ~41 different unknown quantities (9/18/13.5/36/45/54 kcal —
// clean multiples of one another).
//
// Instead: for each existing version sharing this name, check whether a
// SINGLE scale factor r explains the incoming reading as r x that version,
// consistently across energy/protein/carb/fat. If the implied ratios agree
// (within 15% of their median — a coarser, structural check, not a
// precision check), it's the same food at a different amount: reuse that
// food_id and return the derived quantity. Only fork a new version when no
// existing version's ratios are internally consistent — that's the actual
// signature of a different food or a real recipe change.
//
// The quantity itself is expressed in a per-food CUSTOM UNIT ("reported
// serving"), not grams — we don't know the real gram weight, so we don't
// pretend to. Its equivalent_amount is a 100 (placeholder, matching the
// existing per-100 storage convention) until corrected with real-world data
// (e.g. matched against a reference nutrition database later). Correcting
// it only ever means updating that one foods_db_custom_units row — every
// food_log_entries row referencing it (serving_amount = the ratio) is
// automatically correct with no historical rewrite, since the real total is
// always serving_amount x equivalent_amount.
function findOrCreateFood(PDO $pdo, int $userId, int $massDimensionId, string $name,
    ?float $energyKcal, ?float $proteinG, ?float $carbG, ?float $fatG,
    array $micronutrients, array &$nutrientIds, int $gramUnitId, array &$servingUnitCache): array
{
    $existing = $pdo->prepare(
        "SELECT id, version, energy_kcal, total_protein_g, total_carbohydrate_g, total_fat_g
         FROM foods_db WHERE name = ? AND brand_name IS NULL AND dimension_id = ? AND user_id = ?
         ORDER BY COALESCE(version, 0) DESC"
    );
    $existing->execute([$name, $massDimensionId, $userId]);
    $candidates = $existing->fetchAll(PDO::FETCH_ASSOC);

    $impliedRatio = function (?float $incoming, ?float $baseline): ?float {
        if ($incoming === null && $baseline === null) {
            return null; // both absent, no signal either way
        }
        if ($incoming === null || $baseline === null || abs($baseline) < 0.001) {
            return null; // can't compute a ratio against zero/missing baseline
        }
        return $incoming / $baseline;
    };

    foreach ($candidates as $row) {
        $ratios = array_filter([
            $impliedRatio($energyKcal, $row['energy_kcal'] !== null ? (float) $row['energy_kcal'] : null),
            $impliedRatio($proteinG, $row['total_protein_g'] !== null ? (float) $row['total_protein_g'] : null),
            $impliedRatio($carbG, $row['total_carbohydrate_g'] !== null ? (float) $row['total_carbohydrate_g'] : null),
            $impliedRatio($fatG, $row['total_fat_g'] !== null ? (float) $row['total_fat_g'] : null),
        ], fn($r) => $r !== null && $r > 0);

        if (count($ratios) === 0) {
            continue;
        }
        sort($ratios);
        $median = $ratios[intdiv(count($ratios), 2)];
        $consistent = true;
        foreach ($ratios as $r) {
            if (abs($r - $median) > $median * 0.15) {
                $consistent = false;
                break;
            }
        }
        if ($consistent) {
            $foodId = (int) $row['id'];
            $servingUnitId = $servingUnitCache[$foodId] ?? null;
            return [$foodId, false, round($median, 4), $servingUnitId];
        }
    }

    $latestVersion = empty($candidates) ? null : ((int) $candidates[0]['version']);
    $newVersion = $latestVersion === null ? null : ($latestVersion + 1);
    $insert = $pdo->prepare(
        "INSERT INTO foods_db (name, dimension_id, version, group_id, user_id, energy_kcal, total_protein_g, total_carbohydrate_g, total_fat_g)
         VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)"
    );
    $insert->execute([$name, $massDimensionId, $newVersion, $userId, $energyKcal, $proteinG, $carbG, $fatG]);
    $foodId = (int) $pdo->lastInsertId();

    if (!empty($micronutrients)) {
        $insertNutrient = $pdo->prepare("INSERT INTO foods_db_nutrients (food_id, nutrient_id, quantity, unit_id) VALUES (?, ?, ?, ?)");
        foreach ($micronutrients as $nutrientName => $qty) {
            if (!isset($nutrientIds[$nutrientName])) {
                continue;
            }
            $insertNutrient->execute([$foodId, $nutrientIds[$nutrientName], $qty, $gramUnitId]);
        }
    }

    $insertCustomUnit = $pdo->prepare(
        "INSERT INTO foods_db_custom_units (food_id, unit_name, equivalent_amount, is_default) VALUES (?, 'reported serving', 100, TRUE)"
    );
    $insertCustomUnit->execute([$foodId]);
    $customUnitId = (int) $pdo->lastInsertId();
    $insertServingUnit = $pdo->prepare(
        "INSERT INTO lut_serving_unit (label, foods_db_custom_unit_id) VALUES (?, ?)"
    );
    $insertServingUnit->execute(["hc_reported_serving_{$foodId}", $customUnitId]);
    $servingUnitId = (int) $pdo->lastInsertId();
    $servingUnitCache[$foodId] = $servingUnitId;

    return [$foodId, true, 1.0, $servingUnitId];
}

function importNutrition(PDO $hc, PDO $pdo, int $userId, int $ingestionSource, int $massDimensionId,
    int $gramUnitId, array $mealTypeIds, array &$nutrientIds,
    array &$dataSourceIds, PDOStatement $insertDataSourceStmt, array $appNames): void
{
    logLine("--- Nutrition (nutrition_record_table) ---");
    $servingUnitCache = [];
    $insertEntry = $pdo->prepare(
        "INSERT INTO food_log_entries (user_id, start_time, end_time, meal_type_id, food_id, serving_amount, serving_unit_id, data_source_id, ingestion_source_id, api_uid)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    );

    $rowNum = 0;
    $pdo->beginTransaction();
    $stmt = $hc->query("SELECT * FROM nutrition_record_table");
    foreach ($stmt as $row) {
        $rowNum++;
        bumpStat('nutrition', 'rows_seen', 1);
        try {
            $name = trim((string) $row['meal_name']);
            if ($name === '') {
                logLine("WARN nutrition row {$rowNum}: empty meal_name, skipping");
                bumpStat('nutrition', 'skipped_error', 1);
                continue;
            }
            $mealTypeId = hcMealTypeId((int) $row['meal_type'], $mealTypeIds);
            if ($mealTypeId === null) {
                logLine("WARN nutrition row {$rowNum}: unmapped meal_type " . $row['meal_type'] . ", skipping");
                bumpStat('nutrition', 'skipped_error', 1);
                continue;
            }
            $energyKcal = $row['energy'] !== null ? round(((float) $row['energy']) / 1000, 2) : null;
            $proteinG = $row['protein'] !== null ? (float) $row['protein'] : null;
            $carbG = $row['total_carbohydrate'] !== null ? (float) $row['total_carbohydrate'] : null;
            $fatG = $row['total_fat'] !== null ? (float) $row['total_fat'] : null;

            $micronutrients = [];
            foreach (HC_NUTRIENT_COLUMNS as $col => $nutrientName) {
                if ($row[$col] !== null) {
                    $micronutrients[$nutrientName] = (float) $row[$col];
                }
            }

            [$foodId, $wasNewVersion, $servingAmount, $servingUnitId] = findOrCreateFood($pdo, $userId, $massDimensionId, $name,
                $energyKcal, $proteinG, $carbG, $fatG, $micronutrients, $nutrientIds, $gramUnitId, $servingUnitCache);
            bumpStat('nutrition', $wasNewVersion ? 'foods_db_versions_created' : 'foods_db_versions_reused', 1);

            if ($servingUnitId === null) {
                // Matched an existing food_id whose custom-unit wasn't in
                // this run's cache (e.g. created earlier in a prior run) —
                // look it up rather than fail the row.
                $lookup = $pdo->prepare(
                    "SELECT lsu.id FROM lut_serving_unit lsu
                     JOIN foods_db_custom_units fdcu ON fdcu.id = lsu.foods_db_custom_unit_id
                     WHERE fdcu.food_id = ? LIMIT 1"
                );
                $lookup->execute([$foodId]);
                $servingUnitId = (int) $lookup->fetchColumn();
                $servingUnitCache[$foodId] = $servingUnitId;
            }

            $startTime = hcTimeToMysql((int) $row['start_time']);
            $endTime = hcTimeToMysql((int) $row['end_time']);
            $appName = $appNames[(int) $row['app_info_id']] ?? null;
            $dataSourceId = findOrCreateDataSource($appName, $pdo, $dataSourceIds, $insertDataSourceStmt);
            $apiUid = hcUuid($row['uuid']);

            try {
                $insertEntry->execute([$userId, $startTime, $endTime, $mealTypeId, $foodId, $servingAmount, $servingUnitId, $dataSourceId, $ingestionSource, $apiUid]);
                bumpStat('nutrition', 'inserted', 1);
            } catch (PDOException $e) {
                if ((int) ($e->errorInfo[1] ?? 0) === 1062) {
                    bumpStat('nutrition', 'skipped_duplicate', 1);
                    continue;
                }
                throw $e;
            }
        } catch (Throwable $e) {
            logLine("ERROR nutrition row {$rowNum}: " . $e->getMessage());
            bumpStat('nutrition', 'skipped_error', 1);
        }

        if ($rowNum % 500 === 0) {
            $pdo->commit();
            $pdo->beginTransaction();
            logLine("Nutrition progress: {$rowNum} rows processed");
        }
    }
    $pdo->commit();
    logLine("Nutrition done: {$rowNum} rows processed");
}

$massDimensionId = (int) $pdo->query("SELECT id FROM lut_dimension WHERE name='mass'")->fetchColumn();
importNutrition($hc, $pdo, $userId, $ingestionSourceHC, $massDimensionId, $gramUnitId,
    $mealTypeIds, $nutrientIds, $dataSourceIds, $insertDataSource, $appNames);

// ----------------------------------------------------------------------------
// 2 & 3. Weight & height -> measurements
// ----------------------------------------------------------------------------

function importMeasurementSeries(PDO $hc, PDO $pdo, string $hcTable, string $timeCol, string $valueCol,
    float $valueDivisor, string $label, int $userId, int $ingestionSource, int $measurementTypeId,
    int $unitId, array &$dataSourceIds, PDOStatement $insertDataSourceStmt, array &$recordingMethodIds,
    array $appNames): void
{
    logLine("--- {$label} ({$hcTable}) ---");
    $insert = $pdo->prepare(
        "INSERT INTO measurements (user_id, measurement_type_id, reading_time, value, unit_id, data_source_id, recording_method_id, ingestion_source_id, api_uid)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
    );
    $count = 0;
    $pdo->beginTransaction();
    foreach ($hc->query("SELECT * FROM {$hcTable}") as $row) {
        $count++;
        try {
            $readingTime = hcTimeToMysql((int) $row[$timeCol]);
            $value = round(((float) $row[$valueCol]) / $valueDivisor, 4);
            $appName = $appNames[(int) $row['app_info_id']] ?? null;
            $dataSourceId = findOrCreateDataSource($appName, $pdo, $dataSourceIds, $insertDataSourceStmt);
            $recordingMethodId = hcRecordingMethodId((int) $row['recording_method'], $recordingMethodIds);
            $apiUid = hcUuid($row['uuid']);
            try {
                $insert->execute([$userId, $measurementTypeId, $readingTime, $value, $unitId, $dataSourceId, $recordingMethodId, $ingestionSource, $apiUid]);
                bumpStat($label, 'inserted', 1);
            } catch (PDOException $e) {
                if ((int) ($e->errorInfo[1] ?? 0) === 1062) {
                    bumpStat($label, 'skipped_duplicate', 1);
                    continue;
                }
                throw $e;
            }
        } catch (Throwable $e) {
            logLine("ERROR {$label} row: " . $e->getMessage());
            bumpStat($label, 'skipped_error', 1);
        }
        if ($count % 2000 === 0) {
            $pdo->commit();
            $pdo->beginTransaction();
        }
    }
    $pdo->commit();
    logLine("{$label} done: {$count} rows processed");
}

importMeasurementSeries($hc, $pdo, 'weight_record_table', 'time', 'weight', 1.0, 'weight', $userId,
    $ingestionSourceHC, $measurementTypeIds['weight'], $gramUnitId, $dataSourceIds, $insertDataSource,
    $recordingMethodIds, $appNames);

importMeasurementSeries($hc, $pdo, 'height_record_table', 'time', 'height', 0.001, 'height', $userId,
    $ingestionSourceHC, $measurementTypeIds['height'], $mmUnitId, $dataSourceIds, $insertDataSource,
    $recordingMethodIds, $appNames);

// ----------------------------------------------------------------------------
// 4. Steps -> steps_readings
// ----------------------------------------------------------------------------

function importIntervalSeries(PDO $hc, PDO $pdo, string $hcTable, string $timeCol, string $valueCol,
    string $insertSql, callable $rowMapper, string $label, int $batchSize = 2000): void
{
    logLine("--- {$label} ({$hcTable}) ---");
    $buffer = [];
    $flush = function () use (&$buffer, $pdo, $insertSql, $label) {
        if (empty($buffer)) {
            return;
        }
        $ph = implode(',', array_fill(0, count($buffer), '(' . implode(',', array_fill(0, count($buffer[0]), '?')) . ')'));
        $stmt = $pdo->prepare($insertSql . ' VALUES ' . $ph);
        $params = [];
        foreach ($buffer as $r) {
            array_push($params, ...$r);
        }
        $stmt->execute($params);
        $affected = $stmt->rowCount();
        bumpStat($label, 'inserted', $affected);
        bumpStat($label, 'skipped_duplicate', count($buffer) - $affected);
        $buffer = [];
    };

    $count = 0;
    foreach ($hc->query("SELECT * FROM {$hcTable}") as $row) {
        $count++;
        bumpStat($label, 'rows_seen', 1);
        try {
            $mapped = $rowMapper($row);
            if ($mapped !== null) {
                $buffer[] = $mapped;
                if (count($buffer) >= $batchSize) {
                    $flush();
                }
            }
        } catch (Throwable $e) {
            logLine("ERROR {$label} row: " . $e->getMessage());
            bumpStat($label, 'skipped_error', 1);
        }
    }
    $flush();
    logLine("{$label} done: {$count} rows processed");
}

importIntervalSeries($hc, $pdo, 'steps_record_table', 'start_time', 'count',
    "INSERT IGNORE INTO steps_readings (user_id, reading_time, steps, data_source_id, recording_method_id, ingestion_source_id, api_uid)",
    function (array $row) use ($userId, $ingestionSourceHC, &$dataSourceIds, $insertDataSource, $pdo, &$recordingMethodIds, $appNames) {
        $readingTime = hcTimeToMysql((int) $row['end_time']);
        $appName = $appNames[(int) $row['app_info_id']] ?? null;
        $dataSourceId = findOrCreateDataSource($appName, $pdo, $dataSourceIds, $insertDataSource);
        $recordingMethodId = hcRecordingMethodId((int) $row['recording_method'], $recordingMethodIds);
        return [$userId, $readingTime, (int) $row['count'], $dataSourceId, $recordingMethodId, $ingestionSourceHC, hcUuid($row['uuid'])];
    },
    'steps'
);

// ----------------------------------------------------------------------------
// 5. Heart rate -> heart_rate_readings (from heart_rate_record_series_table,
//    joined back to its parent record for device/app/recording-method)
// ----------------------------------------------------------------------------

logLine("--- heart_rate (heart_rate_record_series_table, joined to parent) ---");
$hrParents = [];
foreach ($hc->query("SELECT row_id, app_info_id, recording_method FROM heart_rate_record_table") as $row) {
    $hrParents[(int) $row['row_id']] = $row;
}
logLine("Heart rate: " . count($hrParents) . " parent records, streaming series rows");

importIntervalSeries($hc, $pdo, 'heart_rate_record_series_table', 'epoch_millis', 'beats_per_minute',
    "INSERT IGNORE INTO heart_rate_readings (user_id, reading_time, bpm, data_source_id, recording_method_id, ingestion_source_id)",
    function (array $row) use ($userId, $ingestionSourceHC, &$dataSourceIds, $insertDataSource, $pdo, &$recordingMethodIds, $appNames, &$hrParents) {
        $readingTime = hcTimeToMysql((int) $row['epoch_millis']);
        $parent = $hrParents[(int) $row['parent_key']] ?? null;
        $appName = $parent !== null ? ($appNames[(int) $parent['app_info_id']] ?? null) : null;
        $dataSourceId = findOrCreateDataSource($appName, $pdo, $dataSourceIds, $insertDataSource);
        $recordingMethodId = $parent !== null ? hcRecordingMethodId((int) $parent['recording_method'], $recordingMethodIds) : null;
        return [$userId, $readingTime, (int) $row['beats_per_minute'], $dataSourceId, $recordingMethodId, $ingestionSourceHC];
    },
    'heart_rate',
    5000
);

// ----------------------------------------------------------------------------
// 6. HRV -> heart_rate_variability_readings
// ----------------------------------------------------------------------------

importIntervalSeries($hc, $pdo, 'heart_rate_variability_rmssd_record_table', 'time', 'heart_rate_variability_millis',
    "INSERT IGNORE INTO heart_rate_variability_readings (user_id, reading_time, rmssd_ms, data_source_id, recording_method_id, ingestion_source_id, api_uid)",
    function (array $row) use ($userId, $ingestionSourceHC, &$dataSourceIds, $insertDataSource, $pdo, &$recordingMethodIds, $appNames) {
        $readingTime = hcTimeToMysql((int) $row['time']);
        $appName = $appNames[(int) $row['app_info_id']] ?? null;
        $dataSourceId = findOrCreateDataSource($appName, $pdo, $dataSourceIds, $insertDataSource);
        $recordingMethodId = hcRecordingMethodId((int) $row['recording_method'], $recordingMethodIds);
        return [$userId, $readingTime, round((float) $row['heart_rate_variability_millis'], 2), $dataSourceId, $recordingMethodId, $ingestionSourceHC, hcUuid($row['uuid'])];
    },
    'heart_rate_variability'
);

// ----------------------------------------------------------------------------
// 7. Sleep -> sleep_sessions + sleep_stages
// ----------------------------------------------------------------------------

logLine("--- sleep sessions (sleep_session_record_table) ---");
$insertSleepSession = $pdo->prepare(
    "INSERT INTO sleep_sessions (user_id, start_time, end_time, data_source_id, recording_method_id, ingestion_source_id, api_uid)
     VALUES (?, ?, ?, ?, ?, ?, ?)"
);
// Looked up by (user_id, start_time), not api_uid: a duplicate-key hit can
// now come from either uq_sleep_sessions_api_uid (same-source re-import) or
// uq_sleep_sessions_start (a live-API sync already recorded this same real
// session under its own, different api_uid) - start_time is the one thing
// guaranteed to match the actual colliding row in both cases.
$findSleepSessionByStartTime = $pdo->prepare(
    "SELECT id FROM sleep_sessions WHERE user_id = ? AND start_time = ?"
);
$sleepRowIdToId = [];
$sessionCount = 0;
$pdo->beginTransaction();
foreach ($hc->query("SELECT * FROM sleep_session_record_table") as $row) {
    $sessionCount++;
    bumpStat('sleep_sessions', 'rows_seen', 1);
    try {
        $startTime = hcTimeToMysql((int) $row['start_time']);
        $endTime = hcTimeToMysql((int) $row['end_time']);
        $appName = $appNames[(int) $row['app_info_id']] ?? null;
        $dataSourceId = findOrCreateDataSource($appName, $pdo, $dataSourceIds, $insertDataSource);
        $recordingMethodId = hcRecordingMethodId((int) $row['recording_method'], $recordingMethodIds);
        $apiUid = hcUuid($row['uuid']);
        try {
            $insertSleepSession->execute([$userId, $startTime, $endTime, $dataSourceId, $recordingMethodId, $ingestionSourceHC, $apiUid]);
        } catch (PDOException $e) {
            if ((int) ($e->errorInfo[1] ?? 0) === 1062) {
                bumpStat('sleep_sessions', 'skipped_duplicate', 1);
                // Still record the mapping for an already-known session so
                // its stages remain reachable below — without this, a
                // re-import silently drops every stage for every session it
                // has already seen (real bug, found via a real re-import).
                $findSleepSessionByStartTime->execute([$userId, $startTime]);
                $existingId = $findSleepSessionByStartTime->fetchColumn();
                if ($existingId !== false) {
                    $sleepRowIdToId[(int) $row['row_id']] = (int) $existingId;
                }
                continue;
            }
            throw $e;
        }
        $sleepRowIdToId[(int) $row['row_id']] = (int) $pdo->lastInsertId();
        bumpStat('sleep_sessions', 'inserted', 1);
    } catch (Throwable $e) {
        logLine("ERROR sleep session row_id=" . $row['row_id'] . ": " . $e->getMessage());
        bumpStat('sleep_sessions', 'skipped_error', 1);
    }
    if ($sessionCount % 500 === 0) {
        $pdo->commit();
        $pdo->beginTransaction();
    }
}
$pdo->commit();
logLine("Sleep sessions done: " . count($sleepRowIdToId) . " sessions inserted");

logLine("--- sleep stages (sleep_stages_table) ---");
$buffer = [];
$flushStages = function () use (&$buffer, $pdo) {
    if (empty($buffer)) {
        return;
    }
    $ph = implode(',', array_fill(0, count($buffer), '(?,?,?,?,?,?)'));
    $stmt = $pdo->prepare("INSERT IGNORE INTO sleep_stages (user_id, sleep_session_id, stage_type_id, start_time, end_time, ingestion_source_id) VALUES {$ph}");
    $params = [];
    foreach ($buffer as $r) {
        array_push($params, ...$r);
    }
    $stmt->execute($params);
    $affected = $stmt->rowCount();
    bumpStat('sleep_stages', 'inserted', $affected);
    bumpStat('sleep_stages', 'skipped_duplicate', count($buffer) - $affected);
    $buffer = [];
};
$stageCount = 0;
foreach ($hc->query("SELECT * FROM sleep_stages_table") as $row) {
    $stageCount++;
    bumpStat('sleep_stages', 'rows_seen', 1);
    try {
        $sessionId = $sleepRowIdToId[(int) $row['parent_key']] ?? null;
        if ($sessionId === null) {
            bumpStat('sleep_stages', 'skipped_error', 1);
            continue;
        }
        $stageTypeId = hcSleepStageTypeId((int) $row['stage_type'], $sleepStageTypeIds);
        if ($stageTypeId === null) {
            logLine("WARN sleep stage: unmapped stage_type " . $row['stage_type']);
            bumpStat('sleep_stages', 'skipped_error', 1);
            continue;
        }
        $buffer[] = [$userId, $sessionId, $stageTypeId, hcTimeToMysql((int) $row['stage_start_time']), hcTimeToMysql((int) $row['stage_end_time']), $ingestionSourceHC];
        if (count($buffer) >= 2000) {
            $flushStages();
        }
    } catch (Throwable $e) {
        logLine("ERROR sleep stage: " . $e->getMessage());
        bumpStat('sleep_stages', 'skipped_error', 1);
    }
}
$flushStages();
logLine("Sleep stages done: {$stageCount} rows processed");

// ----------------------------------------------------------------------------
// 8. Exercise -> exercise_sessions
// ----------------------------------------------------------------------------

logLine("--- exercise (exercise_session_record_table) ---");
$insertExercise = $pdo->prepare(
    "INSERT INTO exercise_sessions (user_id, start_time, end_time, activity_name, activity_type_id, has_gps, data_source_id, recording_method_id, ingestion_source_id, api_uid)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
);
$exerciseCount = 0;
$pdo->beginTransaction();
foreach ($hc->query("SELECT * FROM exercise_session_record_table") as $row) {
    $exerciseCount++;
    bumpStat('exercise', 'rows_seen', 1);
    try {
        $startTime = hcTimeToMysql((int) $row['start_time']);
        $endTime = hcTimeToMysql((int) $row['end_time']);
        $activityName = $row['title'] ?? null;
        $activityTypeId = findOrCreateActivityType('HC_' . $row['exercise_type'], $pdo, $activityTypeIds, $insertActivityType);
        $hasGps = ((int) ($row['has_route'] ?? 0)) === 1;
        $appName = $appNames[(int) $row['app_info_id']] ?? null;
        $dataSourceId = findOrCreateDataSource($appName, $pdo, $dataSourceIds, $insertDataSource);
        $recordingMethodId = hcRecordingMethodId((int) $row['recording_method'], $recordingMethodIds);
        $apiUid = hcUuid($row['uuid']);
        try {
            $insertExercise->execute([$userId, $startTime, $endTime, $activityName, $activityTypeId, $hasGps ? 1 : 0, $dataSourceId, $recordingMethodId, $ingestionSourceHC, $apiUid]);
            bumpStat('exercise', 'inserted', 1);
        } catch (PDOException $e) {
            if ((int) ($e->errorInfo[1] ?? 0) === 1062) {
                bumpStat('exercise', 'skipped_duplicate', 1);
                continue;
            }
            throw $e;
        }
    } catch (Throwable $e) {
        logLine("ERROR exercise row_id=" . $row['row_id'] . ": " . $e->getMessage());
        bumpStat('exercise', 'skipped_error', 1);
    }
    if ($exerciseCount % 500 === 0) {
        $pdo->commit();
        $pdo->beginTransaction();
    }
}
$pdo->commit();
logLine("Exercise done: {$exerciseCount} rows processed");

// ----------------------------------------------------------------------------
// Summary
// ----------------------------------------------------------------------------

$elapsed = round(microtime(true) - $startedAt, 1);
logLine("=== Import complete in {$elapsed}s ===");
foreach ($runStats as $category => $stats) {
    $parts = [];
    foreach ($stats as $k => $v) {
        $parts[] = "{$k}={$v}";
    }
    logLine(strtoupper($category) . ': ' . implode(', ', $parts));
}

logLine("=== Post-import row counts ===");
$tables = [
    'foods_db', 'foods_db_nutrients', 'food_log_entries', 'measurements', 'steps_readings',
    'heart_rate_readings', 'heart_rate_variability_readings', 'exercise_sessions',
    'sleep_sessions', 'sleep_stages', 'lut_data_source', 'lut_activity_type',
];
foreach ($tables as $t) {
    $count = $pdo->query("SELECT COUNT(*) FROM {$t}")->fetchColumn();
    logLine("{$t}: {$count}");
}

fclose($logFile);

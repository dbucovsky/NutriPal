<?php

declare(strict_types=1);

// Imports a Google Takeout export into a freshly-initialized NutriPal
// schema (sql/schema.sql + sql/init_lookups.sql already applied, all
// tables empty). Serves as an end-to-end, real-data stress test of the
// schema/triggers, not just a one-off utility — every row inserted here is
// real, and every decision below is logged so the run can be verified
// afterward. See doc/wiki/Database-Schema.md for the source-format notes
// this importer is built against.
//
// Usage: php scripts/import-takeout.php <path-to-takeout.zip>

require __DIR__ . '/../src/Env.php';
require __DIR__ . '/../src/Database.php';

Env::load(__DIR__ . '/../.env');

$zipPath = $argv[1] ?? null;
if ($zipPath === null || !is_file($zipPath)) {
    fwrite(STDERR, "Usage: php import-takeout.php <path-to-takeout.zip>\n");
    exit(1);
}

$logDir = __DIR__ . '/../storage/import-logs';
if (!is_dir($logDir)) {
    mkdir($logDir, 0777, true);
}
$logPath = $logDir . '/takeout-import-' . date('Ymd-His') . '.log';
$logFile = fopen($logPath, 'w');

$runStats = []; // category => ['files' => n, 'rows_seen' => n, 'inserted' => n, 'skipped_duplicate' => n, 'skipped_error' => n]
$droppedNutrients = []; // name => count
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

logLine("=== NutriPal Takeout import starting ===");
logLine("Zip: {$zipPath}");
logLine("Log: {$logPath}");

$pdo = Database::connect();
$appTimezone = new DateTimeZone(Env::get('APP_TIMEZONE', 'America/New_York'));
$utc = new DateTimeZone('UTC');

logLine("Connected to database " . Env::get('DB_NAME'));

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
$unitFactors = [];
foreach ($pdo->query("SELECT id, factor_to_base FROM unit_conversions") as $row) {
    $unitFactors[(int) $row['id']] = (float) $row['factor_to_base'];
}
$ingestionSourceIds = loadLookup($pdo, 'lut_ingestion_source');
$sleepStageTypeIds = loadLookup($pdo, 'lut_sleep_stage_type');
$sleepTypeIds = loadLookup($pdo, 'lut_sleep_type');
$recordingMethodIds = loadLookup($pdo, 'lut_recording_method');
$measurementTypeIds = loadLookup($pdo, 'lut_measurement_type');

$dataSourceIds = loadLookup($pdo, 'lut_data_source');
$activityTypeIds = loadLookup($pdo, 'lut_activity_type');

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

$ingestionSourceTakeout = $ingestionSourceIds['google_takeout'];
$userId = 2; // the one seeded real user (sql/init_lookups.sql)

logLine("Lookup caches loaded: " . count($mealTypeIds) . " meal types, " . count($nutrientIds) . " nutrients, "
    . count($unitIds) . " units, " . count($sleepStageTypeIds) . " sleep stage types, "
    . count($recordingMethodIds) . " recording methods, " . count($measurementTypeIds) . " measurement types");

// ----------------------------------------------------------------------------
// Shared helpers
// ----------------------------------------------------------------------------

function isoToMysql(string $iso): string
{
    // Handles "2026-05-01T00:00:00Z" and fractional-second variants.
    $dt = new DateTimeImmutable($iso);
    return $dt->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s');
}

function legacyLocalToMysqlUtc(string $s, DateTimeZone $localTz): string
{
    // Legacy Fitbit export format "MM/DD/YY HH:MM:SS", no timezone marker.
    // Historically these exports use the account's local timezone —
    // interpreted here as APP_TIMEZONE and converted to UTC for storage,
    // matching every other UTC-stored timestamp in this schema. Logged
    // explicitly since it's an assumption, not a confirmed fact.
    $dt = DateTimeImmutable::createFromFormat('m/d/y H:i:s', $s, $localTz);
    if ($dt === false) {
        throw new RuntimeException("Could not parse legacy timestamp: {$s}");
    }
    return $dt->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s');
}

function fp(array $parts): string
{
    return hash('sha256', implode('|', $parts));
}

function openZipLines(ZipArchive $zip, string $entry, bool $skipHeader = false)
{
    $stream = $zip->getStream($entry);
    if ($stream === false) {
        throw new RuntimeException("Could not open zip entry: {$entry}");
    }
    if ($skipHeader) {
        fgets($stream);
    }
    while (($line = fgets($stream)) !== false) {
        yield rtrim($line, "\r\n");
    }
    fclose($stream);
}

function zipEntriesMatching(ZipArchive $zip, string $pattern): array
{
    $matches = [];
    for ($i = 0; $i < $zip->numFiles; $i++) {
        $name = $zip->getNameIndex($i);
        if ($name !== false && fnmatch($pattern, $name)) {
            $matches[] = $name;
        }
    }
    sort($matches);
    return $matches;
}

$zip = new ZipArchive();
if ($zip->open($zipPath) !== true) {
    logLine("FATAL: could not open zip file");
    exit(1);
}
logLine("Zip opened: " . $zip->numFiles . " entries total");

$root = 'Takeout/Google Health/';

// ----------------------------------------------------------------------------
// 1. Nutrition -> food_log_entries + food_log_nutrients
// ----------------------------------------------------------------------------

function importNutrition(ZipArchive $zip, PDO $pdo, string $root, int $userId, int $ingestionSource,
    array $mealTypeIds, array &$nutrientIds, array $unitIds, array $unitFactors,
    array &$dataSourceIds, PDOStatement $insertDataSourceStmt, array &$droppedNutrients): void
{
    $entry = $root . 'Physical Activity_GoogleData/nutrition_log.csv';
    logLine("--- Nutrition: {$entry} ---");
    bumpStat('nutrition', 'files', 1);

    $insertEntry = $pdo->prepare(
        "INSERT INTO food_log_entries
            (user_id, start_time, end_time, brand_name, food_name, meal_type_id, energy_kcal, is_energy_estimated,
             total_protein_g, total_carbohydrate_g, total_fat_g, data_source_id, ingestion_source_id, fingerprint)
         VALUES (?, ?, ?, ?, ?, ?, ?, TRUE, ?, ?, NULL, ?, ?, ?)"
    );
    $insertNutrient = $pdo->prepare(
        "INSERT INTO food_log_nutrients (user_id, food_log_entry_id, nutrient_id, quantity, unit_id, value_type_id)
         VALUES (?, ?, ?, ?, ?, 1)"
    );

    $lines = openZipLines($zip, $entry, true);

    $rowNum = 0;
    $pdo->beginTransaction();
    foreach ($lines as $line) {
        if ($line === '') {
            continue;
        }
        $rowNum++;
        bumpStat('nutrition', 'rows_seen', 1);
        $row = str_getcsv($line);
        [$startRaw, $endRaw, $brand, $foodName, $mealType, $nutrientsStr, $dataSource] = array_pad($row, 7, null);

        try {
            $mealTypeId = $mealTypeIds[$mealType] ?? null;
            if ($mealTypeId === null) {
                logLine("WARN nutrition row {$rowNum}: unknown meal type '{$mealType}', skipping row");
                bumpStat('nutrition', 'skipped_error', 1);
                continue;
            }

            $startTime = isoToMysql($startRaw);
            $endTime = isoToMysql($endRaw);
            $dataSourceId = findOrCreateDataSource($dataSource, $pdo, $dataSourceIds, $insertDataSourceStmt);

            $proteinG = null;
            $carbG = null;
            $fatForEnergyG = 0.0;
            $childNutrients = []; // [nutrientId, quantity, unitId]
            $anyMacroMissing = false;

            foreach (explode('; ', trim($nutrientsStr)) as $pair) {
                if ($pair === '') {
                    continue;
                }
                [$name, $rest] = array_pad(explode(': ', $pair, 2), 2, null);
                if ($name === null || $rest === null) {
                    continue;
                }
                if (strtoupper(trim($rest)) === 'N/A') {
                    // Confirmed real and common (~21% of rows): Google didn't
                    // compute this nutrient for this food at all. Treated as
                    // genuinely unreported, not zero — same as an absent
                    // nutrient, not logged per-occurrence (too common to be
                    // a warning), just counted for the summary.
                    bumpStat('nutrition', 'nutrients_reported_na', 1);
                    continue;
                }

                [$rawValue, $unitName] = array_pad(explode(' ', trim($rest), 2), 2, null);
                $value = (float) $rawValue;
                $unitKey = strtolower((string) $unitName);
                $unitId = $unitIds[$unitKey] ?? null;
                $grams = $unitId !== null ? $value * $unitFactors[$unitId] : $value;

                if ($name === 'PROTEIN') {
                    $proteinG = $grams;
                } elseif ($name === 'CARBOHYDRATES') {
                    $carbG = $grams;
                } elseif ($name === 'SATURATED_FAT' || $name === 'TRANS_FAT') {
                    $fatForEnergyG += $grams;
                    if (isset($nutrientIds[$name]) && $unitId !== null) {
                        $childNutrients[] = [$nutrientIds[$name], $value, $unitId];
                    }
                } elseif (isset($nutrientIds[$name])) {
                    if ($unitId === null) {
                        logLine("WARN nutrition row {$rowNum}: unknown unit '{$unitName}' for nutrient {$name}, skipping that nutrient");
                        continue;
                    }
                    $childNutrients[] = [$nutrientIds[$name], $value, $unitId];
                } else {
                    $droppedNutrients[$name] = ($droppedNutrients[$name] ?? 0) + 1;
                    bumpStat('nutrition', 'dropped_nutrients', 1);
                }
            }

            if ($proteinG === null || $carbG === null) {
                $anyMacroMissing = true;
            }
            $energyKcal = round(4 * ($proteinG ?? 0) + 4 * ($carbG ?? 0) + 9 * $fatForEnergyG, 2);
            if ($anyMacroMissing) {
                bumpStat('nutrition', 'incomplete_macro_estimate', 1);
            }

            $fingerprint = fp([
                $startTime, $endTime, strtolower(trim((string) $foodName)),
                strtolower(trim($mealType)), strtolower(trim((string) $brand)),
            ]);

            try {
                $insertEntry->execute([
                    $userId, $startTime, $endTime, ($brand !== '' ? $brand : null), $foodName, $mealTypeId,
                    $energyKcal, $proteinG, $carbG, $dataSourceId, $ingestionSource, $fingerprint,
                ]);
            } catch (PDOException $e) {
                if ($e->getCode() === '23000') {
                    bumpStat('nutrition', 'skipped_duplicate', 1);
                    continue;
                }
                throw $e;
            }

            $entryId = (int) $pdo->lastInsertId();
            bumpStat('nutrition', 'inserted', 1);

            foreach ($childNutrients as [$nutrientId, $qty, $unitId]) {
                $insertNutrient->execute([$userId, $entryId, $nutrientId, $qty, $unitId]);
                bumpStat('nutrition', 'nutrient_rows_inserted', 1);
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

importNutrition($zip, $pdo, $root, $userId, $ingestionSourceTakeout, $mealTypeIds, $nutrientIds,
    $unitIds, $unitFactors, $dataSourceIds, $insertDataSource, $droppedNutrients);

// ----------------------------------------------------------------------------
// 2 & 3. Weight & height -> measurements
// ----------------------------------------------------------------------------

function importScalarSeries(ZipArchive $zip, PDO $pdo, string $entry, string $label, int $userId,
    int $ingestionSource, int $measurementTypeId, int $unitId, float $valueDivisor,
    array &$dataSourceIds, PDOStatement $insertDataSourceStmt, string $measurementTypeName): void
{
    logLine("--- {$label}: {$entry} ---");
    bumpStat($label, 'files', 1);

    $insert = $pdo->prepare(
        "INSERT IGNORE INTO measurements
            (user_id, measurement_type_id, reading_time, value, unit_id, data_source_id, ingestion_source_id, fingerprint)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    );

    $lines = openZipLines($zip, $entry, true);

    $count = 0;
    $pdo->beginTransaction();
    foreach ($lines as $line) {
        if ($line === '') {
            continue;
        }
        $row = str_getcsv($line);
        [$tsRaw, $rawValue, $dataSource] = array_pad($row, 3, null);
        try {
            $readingTime = isoToMysql($tsRaw);
            $value = (float) $rawValue / $valueDivisor;
            $dataSourceId = findOrCreateDataSource($dataSource, $pdo, $dataSourceIds, $insertDataSourceStmt);
            $fingerprint = fp([$readingTime, $measurementTypeName, $value]);
            $insert->execute([$userId, $measurementTypeId, $readingTime, $value, $unitId, $dataSourceId, $ingestionSource, $fingerprint]);
            if ($insert->rowCount() > 0) {
                bumpStat($label, 'inserted', 1);
            } else {
                bumpStat($label, 'skipped_duplicate', 1);
            }
            $count++;
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

importScalarSeries(
    $zip, $pdo, $root . 'Physical Activity_GoogleData/weight.csv', 'weight', $userId,
    $ingestionSourceTakeout, $measurementTypeIds['weight'], $unitIds['gram'], 1.0,
    $dataSourceIds, $insertDataSource, 'weight'
);

importScalarSeries(
    $zip, $pdo, $root . 'Physical Activity_GoogleData/height.csv', 'height', $userId,
    $ingestionSourceTakeout, $measurementTypeIds['height'], $unitIds['millimeter'], 1.0,
    $dataSourceIds, $insertDataSource, 'height'
);

// ----------------------------------------------------------------------------
// 4. Steps -> steps_readings
// ----------------------------------------------------------------------------

function importBatchedSeries(ZipArchive $zip, PDO $pdo, array $entries, string $label,
    string $insertSql, callable $rowMapper, int $batchSize = 2000): void
{
    $buffer = [];
    $flush = function () use (&$buffer, $pdo, $insertSql, $label, $batchSize) {
        if (empty($buffer)) {
            return;
        }
        $placeholders = implode(',', array_fill(0, count($buffer), '(' . implode(',', array_fill(0, count($buffer[0]), '?')) . ')'));
        $stmt = $pdo->prepare($insertSql . ' VALUES ' . $placeholders);
        $params = [];
        foreach ($buffer as $row) {
            array_push($params, ...$row);
        }
        $stmt->execute($params);
        $affected = $stmt->rowCount();
        bumpStat($label, 'inserted', $affected);
        bumpStat($label, 'skipped_duplicate', count($buffer) - $affected);
        $buffer = [];
    };

    foreach ($entries as $entry) {
        logLine("--- {$label}: {$entry} ---");
        bumpStat($label, 'files', 1);
        $lines = openZipLines($zip, $entry, true);
        $fileRows = 0;
        foreach ($lines as $line) {
            if ($line === '') {
                continue;
            }
            $row = str_getcsv($line);
            try {
                $mapped = $rowMapper($row);
                if ($mapped !== null) {
                    $buffer[] = $mapped;
                    $fileRows++;
                    bumpStat($label, 'rows_seen', 1);
                    if (count($buffer) >= $batchSize) {
                        $flush();
                    }
                }
            } catch (Throwable $e) {
                logLine("ERROR {$label} row in {$entry}: " . $e->getMessage());
                bumpStat($label, 'skipped_error', 1);
            }
        }
        $flush();
        logLine("{$label} file done ({$fileRows} rows): {$entry}");
    }
}

// (Steps and heart rate run LAST, after every other category — see below —
// so the small/fast categories can be verified before the two genuinely
// large-volume imports begin.)

// ----------------------------------------------------------------------------
// 6. Heart rate variability -> heart_rate_variability_readings
//    (Takeout also reports a standard-deviation-ms column here, which has
//    no corresponding schema column and is intentionally not imported —
//    logged as a known gap, not a schema change made mid-import.)
// ----------------------------------------------------------------------------

$hrvEntries = zipEntriesMatching($zip, $root . 'Physical Activity_GoogleData/heart_rate_variability_????-??-??.csv');
logLine("NOTE: Takeout's heart_rate_variability files also include a 'standard deviation milliseconds' column with no schema column — not imported, logged here as a known gap.");
importBatchedSeries($zip, $pdo, $hrvEntries, 'heart_rate_variability',
    "INSERT IGNORE INTO heart_rate_variability_readings (user_id, reading_time, rmssd_ms, data_source_id, ingestion_source_id, fingerprint)",
    function (array $row) use ($userId, $ingestionSourceTakeout, &$dataSourceIds, $insertDataSource, $pdo) {
        [$tsRaw, $rmssd, $stdev, $dataSource] = array_pad($row, 4, null);
        $readingTime = isoToMysql($tsRaw);
        $rmssdVal = round((float) $rmssd, 2);
        $dataSourceId = findOrCreateDataSource($dataSource, $pdo, $dataSourceIds, $insertDataSource);
        $fingerprint = fp([$readingTime, $rmssdVal]);
        return [$userId, $readingTime, $rmssdVal, $dataSourceId, $ingestionSourceTakeout, $fingerprint];
    }
);

// ----------------------------------------------------------------------------
// 7. Exercise -> exercise_sessions (legacy Fitbit JSON, local-time timestamps)
// ----------------------------------------------------------------------------

function importExercise(ZipArchive $zip, PDO $pdo, string $root, int $userId, int $ingestionSource,
    DateTimeZone $localTz, array &$activityTypeIds, PDOStatement $insertActivityTypeStmt,
    array &$dataSourceIds, PDOStatement $insertDataSourceStmt): void
{
    $entries = zipEntriesMatching($zip, $root . 'Global Export Data/exercise-*.json');
    logLine("Exercise: " . count($entries) . " files, legacy local-time format — timestamps interpreted as APP_TIMEZONE and converted to UTC (logged assumption, see doc/wiki/Database-Schema.md).");

    $insert = $pdo->prepare(
        "INSERT IGNORE INTO exercise_sessions
            (user_id, log_id, start_time, end_time, activity_name, activity_type_id, duration_ms, active_duration_ms,
             calories, steps, average_heart_rate, has_gps, data_source_id, ingestion_source_id, fingerprint, raw_details)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    );

    foreach ($entries as $entry) {
        logLine("--- exercise: {$entry} ---");
        bumpStat('exercise', 'files', 1);
        $stream = $zip->getStream($entry);
        $json = stream_get_contents($stream);
        fclose($stream);
        $sessions = json_decode($json, true);
        if (!is_array($sessions)) {
            logLine("ERROR exercise file did not decode as an array: {$entry}");
            bumpStat('exercise', 'skipped_error', 1);
            continue;
        }
        foreach ($sessions as $s) {
            bumpStat('exercise', 'rows_seen', 1);
            try {
                $logId = (string) $s['logId'];
                $startTime = legacyLocalToMysqlUtc($s['startTime'], $localTz);
                $durationMs = (int) ($s['duration'] ?? 0);
                $endTime = (new DateTimeImmutable($startTime, new DateTimeZone('UTC')))
                    ->modify('+' . $durationMs . ' milliseconds')
                    ->format('Y-m-d H:i:s');
                $activityName = $s['activityName'] ?? null;
                $activityTypeId = findOrCreateActivityType(
                    isset($s['activityTypeId']) ? (string) $s['activityTypeId'] : $activityName,
                    $pdo, $activityTypeIds, $insertActivityTypeStmt
                );
                $dataSourceId = findOrCreateDataSource($s['source']['name'] ?? null, $pdo, $dataSourceIds, $insertDataSourceStmt);
                $hasGps = !empty($s['hasGps']);
                $fingerprint = fp([$logId]);

                $insert->execute([
                    $userId, $logId, $startTime, $endTime, $activityName, $activityTypeId,
                    $durationMs, (int) ($s['activeDuration'] ?? $durationMs),
                    isset($s['calories']) ? (int) $s['calories'] : null,
                    isset($s['steps']) ? (int) $s['steps'] : null,
                    isset($s['averageHeartRate']) ? (int) $s['averageHeartRate'] : null,
                    $hasGps ? 1 : 0, $dataSourceId, $ingestionSource, $fingerprint,
                    json_encode(['logType' => $s['logType'] ?? null, 'heartRateZones' => $s['heartRateZones'] ?? null, 'activeZoneMinutes' => $s['activeZoneMinutes'] ?? null]),
                ]);
                if ($insert->rowCount() > 0) {
                    bumpStat('exercise', 'inserted', 1);
                } else {
                    bumpStat('exercise', 'skipped_duplicate', 1);
                }
            } catch (Throwable $e) {
                logLine("ERROR exercise session (logId=" . ($s['logId'] ?? '?') . "): " . $e->getMessage());
                bumpStat('exercise', 'skipped_error', 1);
            }
        }
    }
    logLine("Exercise done");
}

importExercise($zip, $pdo, $root, $userId, $ingestionSourceTakeout, $appTimezone,
    $activityTypeIds, $insertActivityType, $dataSourceIds, $insertDataSource);

// ----------------------------------------------------------------------------
// 8. Sleep -> sleep_sessions + sleep_stages, then merge in UserSleepScores
// ----------------------------------------------------------------------------

function importSleepSessions(ZipArchive $zip, PDO $pdo, string $root, int $userId, int $ingestionSource,
    array $sleepTypeIds, array $recordingMethodIds, array &$dataSourceIds, PDOStatement $insertDataSourceStmt): array
{
    $entries = zipEntriesMatching($zip, $root . 'Health Fitness Data_GoogleData/UserSleeps_*.csv');
    logLine("Sleep sessions: " . count($entries) . " files");
    $sleepIdToRowId = [];

    $insert = $pdo->prepare(
        "INSERT INTO sleep_sessions
            (user_id, sleep_id, sleep_type_id, start_time, end_time, minutes_in_sleep_period, minutes_asleep,
             minutes_awake, minutes_to_fall_asleep, minutes_after_wake_up, minutes_longest_awakening,
             minutes_to_persistent_sleep, recording_method_id, ingestion_source_id, fingerprint)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    );

    foreach ($entries as $entry) {
        logLine("--- sleep sessions: {$entry} ---");
        bumpStat('sleep_sessions', 'files', 1);
        $lines = openZipLines($zip, $entry, true);
        foreach ($lines as $line) {
            if ($line === '') {
                continue;
            }
            $row = str_getcsv($line);
            [$sleepId, $sleepType, $minInPeriod, $minAfterWake, $minToFall, $minAsleep, $minAwake,
                $minLongestAwakening, $minToPersistent, $startOffset, $sleepStart, $endOffset, $sleepEnd,
                $recMethod, $algoVer, $created, $updated] = array_pad($row, 17, null);
            bumpStat('sleep_sessions', 'rows_seen', 1);
            try {
                $sleepTypeId = $sleepTypeIds[$sleepType] ?? null;
                if ($sleepTypeId === null) {
                    logLine("WARN sleep session {$sleepId}: unknown sleep_type '{$sleepType}', skipping");
                    bumpStat('sleep_sessions', 'skipped_error', 1);
                    continue;
                }
                $startTime = isoToMysql($sleepStart);
                $endTime = isoToMysql($sleepEnd);
                $recordingMethodId = $recordingMethodIds[$recMethod] ?? null;
                $fingerprint = fp([$sleepId]);

                try {
                    $insert->execute([
                        $userId, $sleepId, $sleepTypeId, $startTime, $endTime,
                        (int) $minInPeriod, (int) $minAsleep, (int) $minAwake, (int) $minToFall, (int) $minAfterWake,
                        (int) $minLongestAwakening, (int) $minToPersistent, $recordingMethodId, $ingestionSource, $fingerprint,
                    ]);
                } catch (PDOException $e) {
                    if ($e->getCode() === '23000') {
                        bumpStat('sleep_sessions', 'skipped_duplicate', 1);
                        continue;
                    }
                    throw $e;
                }
                $sleepIdToRowId[$sleepId] = (int) $pdo->lastInsertId();
                bumpStat('sleep_sessions', 'inserted', 1);
            } catch (Throwable $e) {
                logLine("ERROR sleep session {$sleepId}: " . $e->getMessage());
                bumpStat('sleep_sessions', 'skipped_error', 1);
            }
        }
    }
    logLine("Sleep sessions done: " . count($sleepIdToRowId) . " sessions inserted");
    return $sleepIdToRowId;
}

function importSleepStages(ZipArchive $zip, PDO $pdo, string $root, int $userId, int $ingestionSource,
    array $sleepIdToRowId, array $sleepStageTypeIds): void
{
    $entries = zipEntriesMatching($zip, $root . 'Health Fitness Data_GoogleData/UserSleepStages_*.csv');
    logLine("Sleep stages: " . count($entries) . " files");

    $buffer = [];
    $flush = function () use (&$buffer, $pdo, $insert) {
        if (empty($buffer)) {
            return;
        }
        $ph = implode(',', array_fill(0, count($buffer), '(?,?,?,?,?,?,?,?)'));
        $stmt = $pdo->prepare(
            "INSERT IGNORE INTO sleep_stages (user_id, sleep_session_id, sleep_stage_id, stage_type_id, start_time, end_time, ingestion_source_id, fingerprint) VALUES {$ph}"
        );
        $params = [];
        foreach ($buffer as $row) {
            array_push($params, ...$row);
        }
        $stmt->execute($params);
        $affected = $stmt->rowCount();
        bumpStat('sleep_stages', 'inserted', $affected);
        bumpStat('sleep_stages', 'skipped_duplicate', count($buffer) - $affected);
        $buffer = [];
    };

    foreach ($entries as $entry) {
        logLine("--- sleep stages: {$entry} ---");
        bumpStat('sleep_stages', 'files', 1);
        $lines = openZipLines($zip, $entry, true);
        foreach ($lines as $line) {
            if ($line === '') {
                continue;
            }
            $row = str_getcsv($line);
            [$sleepId, $stageId, $stageType, $startOffset, $stageStart, $endOffset, $stageEnd] = array_pad($row, 7, null);
            bumpStat('sleep_stages', 'rows_seen', 1);
            try {
                $sessionRowId = $sleepIdToRowId[$sleepId] ?? null;
                if ($sessionRowId === null) {
                    logLine("WARN sleep stage {$stageId}: parent sleep session {$sleepId} not found, skipping");
                    bumpStat('sleep_stages', 'skipped_error', 1);
                    continue;
                }
                $stageTypeId = $sleepStageTypeIds[$stageType] ?? null;
                if ($stageTypeId === null) {
                    logLine("WARN sleep stage {$stageId}: unknown stage type '{$stageType}', skipping");
                    bumpStat('sleep_stages', 'skipped_error', 1);
                    continue;
                }
                $startTime = isoToMysql($stageStart);
                $endTime = isoToMysql($stageEnd);
                $fingerprint = fp([$sessionRowId, $startTime, $endTime, $stageType]);
                $buffer[] = [$userId, $sessionRowId, $stageId, $stageTypeId, $startTime, $endTime, $ingestionSource, $fingerprint];
                if (count($buffer) >= 2000) {
                    $flush();
                }
            } catch (Throwable $e) {
                logLine("ERROR sleep stage {$stageId}: " . $e->getMessage());
                bumpStat('sleep_stages', 'skipped_error', 1);
            }
        }
    }
    $flush();
    logLine("Sleep stages done");
}

function importSleepScores(ZipArchive $zip, PDO $pdo, string $root, array $sleepIdToRowId): void
{
    $entries = zipEntriesMatching($zip, $root . 'Health Fitness Data_GoogleData/UserSleepScores_*.csv');
    logLine("Sleep scores: " . count($entries) . " files");

    $update = $pdo->prepare(
        "UPDATE sleep_sessions SET overall_score=?, duration_score=?, composition_score=?, revitalization_score=?,
            resting_heart_rate=?, changed_by=? WHERE id=?"
    );

    foreach ($entries as $entry) {
        logLine("--- sleep scores: {$entry} ---");
        bumpStat('sleep_scores', 'files', 1);
        $lines = openZipLines($zip, $entry, true);
        foreach ($lines as $line) {
            if ($line === '') {
                continue;
            }
            $row = str_getcsv($line);
            [$sleepId, $scoreId, $dataSource, $scoreOffset, $scoreTime, $overall, $duration, $composition,
                $revitalization, $sleepTimeMin, $deepMin, $remPct, $restingHr] = array_pad($row, 13, null);
            bumpStat('sleep_scores', 'rows_seen', 1);
            try {
                $sessionRowId = $sleepIdToRowId[$sleepId] ?? null;
                if ($sessionRowId === null) {
                    bumpStat('sleep_scores', 'skipped_error', 1);
                    continue;
                }
                $norm = fn($v) => ($v === null || (float) $v < 0) ? null : round((float) $v, 2);
                $update->execute([
                    $norm($overall), $norm($duration), $norm($composition), $norm($revitalization),
                    $restingHr !== null && $restingHr !== '' ? (int) $restingHr : null,
                    'import-takeout.php (sleep score merge)',
                    $sessionRowId,
                ]);
                bumpStat('sleep_scores', 'merged', 1);
            } catch (Throwable $e) {
                logLine("ERROR sleep score {$scoreId}: " . $e->getMessage());
                bumpStat('sleep_scores', 'skipped_error', 1);
            }
        }
    }
    logLine("Sleep scores done");
}

$sleepIdToRowId = importSleepSessions($zip, $pdo, $root, $userId, $ingestionSourceTakeout,
    $sleepTypeIds, $recordingMethodIds, $dataSourceIds, $insertDataSource);
importSleepStages($zip, $pdo, $root, $userId, $ingestionSourceTakeout, $sleepIdToRowId, $sleepStageTypeIds);
importSleepScores($zip, $pdo, $root, $sleepIdToRowId);

// ----------------------------------------------------------------------------
// 4. Steps -> steps_readings (large volume, run late — see note above)
// ----------------------------------------------------------------------------

$stepsEntries = zipEntriesMatching($zip, $root . 'Physical Activity_GoogleData/steps_????-??-??.csv');
importBatchedSeries($zip, $pdo, $stepsEntries, 'steps',
    "INSERT IGNORE INTO steps_readings (user_id, reading_time, steps, data_source_id, ingestion_source_id, fingerprint)",
    function (array $row) use ($userId, $ingestionSourceTakeout, &$dataSourceIds, $insertDataSource, $pdo) {
        [$tsRaw, $steps, $dataSource] = array_pad($row, 3, null);
        $readingTime = isoToMysql($tsRaw);
        $stepsInt = (int) $steps;
        $dataSourceId = findOrCreateDataSource($dataSource, $pdo, $dataSourceIds, $insertDataSource);
        $fingerprint = fp([$readingTime, $stepsInt]);
        return [$userId, $readingTime, $stepsInt, $dataSourceId, $ingestionSourceTakeout, $fingerprint];
    }
);

// ----------------------------------------------------------------------------
// 5. Heart rate -> heart_rate_readings (the big one — ~1,150 daily files,
// potentially 10-16 million rows; run last by design)
// ----------------------------------------------------------------------------

$heartRateEntries = zipEntriesMatching($zip, $root . 'Physical Activity_GoogleData/heart_rate_????-??-??.csv');
logLine("Heart rate: " . count($heartRateEntries) . " daily files to process");
importBatchedSeries($zip, $pdo, $heartRateEntries, 'heart_rate',
    "INSERT IGNORE INTO heart_rate_readings (user_id, reading_time, bpm, data_source_id, ingestion_source_id, fingerprint)",
    function (array $row) use ($userId, $ingestionSourceTakeout, &$dataSourceIds, $insertDataSource, $pdo) {
        [$tsRaw, $bpm, $dataSource] = array_pad($row, 3, null);
        $readingTime = isoToMysql($tsRaw);
        $bpmInt = (int) round((float) $bpm);
        $dataSourceId = findOrCreateDataSource($dataSource, $pdo, $dataSourceIds, $insertDataSource);
        $fingerprint = fp([$readingTime, $bpmInt]);
        return [$userId, $readingTime, $bpmInt, $dataSourceId, $ingestionSourceTakeout, $fingerprint];
    },
    5000
);

// ----------------------------------------------------------------------------
// Summary
// ----------------------------------------------------------------------------

$zip->close();
$elapsed = round(microtime(true) - $startedAt, 1);

logLine("=== Import complete in {$elapsed}s ===");
foreach ($runStats as $category => $stats) {
    $parts = [];
    foreach ($stats as $k => $v) {
        $parts[] = "{$k}={$v}";
    }
    logLine(strtoupper($category) . ': ' . implode(', ', $parts));
}
if (!empty($droppedNutrients)) {
    arsort($droppedNutrients);
    logLine('Dropped nutrient names (not in lut_nutrient): ' . json_encode($droppedNutrients));
}

logLine("=== Post-import row counts ===");
$tables = [
    'food_log_entries', 'food_log_nutrients', 'measurements', 'steps_readings',
    'heart_rate_readings', 'heart_rate_variability_readings', 'exercise_sessions',
    'sleep_sessions', 'sleep_stages', 'lut_data_source', 'lut_activity_type',
];
foreach ($tables as $t) {
    $count = $pdo->query("SELECT COUNT(*) FROM {$t}")->fetchColumn();
    logLine("{$t}: {$count}");
}

fclose($logFile);

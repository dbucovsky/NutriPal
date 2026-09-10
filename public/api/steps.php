<?php

declare(strict_types=1);

// GET /api/steps.php?user_id=2&date=YYYY-MM-DD&view=day|week|month|year|custom&end_date=YYYY-MM-DD
// Daily step totals for the requested local day/range. view defaults to
// "day"; end_date is only used, and required, for view=custom.
//
// steps_readings has a real, still-open cross-source duplication problem
// (documented in doc/wiki/Database-Schema.md's Open Items): Health Connect
// bulk imports and the live Google Health API sync each independently
// report steps for overlapping real time windows, at different
// reading_times, so summing every row for a day double- or triple-counts.
// Confirmed directly against real data: 2026-09-09 has a live-API "Charge
// 5" stream reporting 16,830 steps AND a live-API "HEALTH_CONNECT" stream
// reporting 6,380 steps for the SAME day - naively summing both would
// overcount by more than a third.
//
// This does not attempt the full reconciliation that would be needed to
// fix that properly (like the food_log_entries/sleep/exercise/measurements
// cross-source work elsewhere in this project) - that's a bigger, separate
// effort. Instead, per day: use whichever single data_source_id reported
// the MOST steps that day, regardless of which pipeline it came from (a
// device worn/carried all day should naturally out-report a partial one).
// A first attempt preferred the live API's own sources whenever present at
// all, falling back to Health Connect only when the API had nothing that
// day - but real data disproved that: 2026-09-07 has a live-API source
// reporting only 1,381 steps while a same-day Health-Connect-imported
// source reports 16,419 - clearly the fuller day. Highest-count-wins
// avoids privileging one pipeline over the other for no real reason. This
// is a disclosed heuristic, not a real fix - see the Known limitations
// note in CHANGELOG.md.

require_once __DIR__ . '/../../src/Env.php';
require_once __DIR__ . '/../../src/Database.php';
require_once __DIR__ . '/../../src/LocalDay.php';

Env::load(__DIR__ . '/../../.env');
header('Content-Type: application/json');

$userId = isset($_GET['user_id']) ? (int) $_GET['user_id'] : 0;
if ($userId <= 0) {
    http_response_code(400);
    echo json_encode(['error' => 'user_id is required']);
    exit;
}

$view = $_GET['view'] ?? 'day';
$timezone = Env::get('APP_TIMEZONE', 'UTC');

try {
    [$startDate, $endDate, $rangeStart, $rangeEnd] = LocalDay::resolveRange($timezone, $view, $_GET['date'] ?? null, $_GET['end_date'] ?? null);
} catch (Exception $e) {
    http_response_code(400);
    echo json_encode(['error' => 'invalid date']);
    exit;
}

$pdo = Database::connect();

$stmt = $pdo->prepare(
    "SELECT sr.reading_time, sr.steps, sr.data_source_id, ds.name AS data_source_name
     FROM steps_readings sr
     LEFT JOIN lut_data_source ds ON ds.id = sr.data_source_id
     WHERE sr.user_id = ? AND sr.reading_time >= ? AND sr.reading_time < ?"
);
$stmt->execute([$userId, $rangeStart, $rangeEnd]);

// Per local day: totals grouped by data_source_id.
$byDate = [];
foreach ($stmt as $row) {
    $localDate = LocalDay::toLocalDate($timezone, $row['reading_time']);
    $sourceKey = $row['data_source_id'] ?? 'null';
    $sourceName = $row['data_source_name'] ?? 'Unknown';
    $bucket = &$byDate[$localDate][$sourceKey];
    if (!isset($bucket)) {
        $bucket = ['name' => $sourceName, 'steps' => 0];
    }
    $bucket['steps'] += (int) $row['steps'];
    unset($bucket);
}

$days = [];
foreach ($byDate as $localDate => $sources) {
    $chosenKey = null;
    $chosen = null;
    foreach ($sources as $sourceKey => $source) {
        if ($chosen === null || $source['steps'] > $chosen['steps']) {
            $chosen = $source;
            $chosenKey = $sourceKey;
        }
    }

    $otherSources = [];
    foreach ($sources as $sourceKey => $source) {
        if ($sourceKey === $chosenKey) {
            continue;
        }
        $otherSources[] = ['name' => $source['name'], 'steps' => $source['steps']];
    }

    $days[] = [
        'date' => $localDate,
        'steps' => $chosen['steps'],
        'source' => $chosen['name'],
        'other_sources' => $otherSources,
    ];
}

echo json_encode([
    'view' => $view,
    'start_date' => $startDate,
    'end_date' => $endDate,
    'days' => $days,
]);

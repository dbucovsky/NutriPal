<?php

declare(strict_types=1);

// GET /api/heart-rate.php?user_id=2&date=YYYY-MM-DD
// Summary stats (min/max/avg bpm, resting HR, avg HRV) plus a chart-ready
// series bucketed into 10-minute averages — raw per-reading data can run
// into the tens of thousands of rows/day, too dense to chart directly.
// Also returns exercise/sleep periods that OVERLAP this local day at all
// (not just ones that start/end on it, unlike exercise.php/sleep.php's own
// day-assignment rules) so the frontend can overlay them on the same
// minute-of-day timeline as the bpm chart.

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

try {
    [$localDate, $dayStart, $dayEnd] = LocalDay::resolve(Env::get('APP_TIMEZONE', 'UTC'), $_GET['date'] ?? null);
} catch (Exception $e) {
    http_response_code(400);
    echo json_encode(['error' => 'invalid date']);
    exit;
}

$pdo = Database::connect();

$summaryStmt = $pdo->prepare(
    "SELECT MIN(bpm) AS min_bpm, MAX(bpm) AS max_bpm, AVG(bpm) AS avg_bpm, COUNT(*) AS n
     FROM heart_rate_readings WHERE user_id = ? AND reading_time >= ? AND reading_time < ?"
);
$summaryStmt->execute([$userId, $dayStart, $dayEnd]);
$summary = $summaryStmt->fetch(PDO::FETCH_ASSOC);

$restingStmt = $pdo->prepare('SELECT bpm FROM daily_resting_heart_rate WHERE user_id = ? AND reading_date = ?');
$restingStmt->execute([$userId, $localDate]);
$restingBpm = $restingStmt->fetchColumn();

$hrvStmt = $pdo->prepare(
    'SELECT AVG(rmssd_ms) AS avg_hrv FROM heart_rate_variability_readings
     WHERE user_id = ? AND reading_time >= ? AND reading_time < ?'
);
$hrvStmt->execute([$userId, $dayStart, $dayEnd]);
$avgHrv = $hrvStmt->fetchColumn();

// 10-minute buckets, indexed by seconds-since-day-start / 600 — dense
// enough for a smooth day-shaped line, sparse enough to chart instantly
// regardless of how many raw readings the source actually reported.
$seriesStmt = $pdo->prepare(
    "SELECT FLOOR(TIMESTAMPDIFF(SECOND, ?, reading_time) / 600) AS bucket_idx, AVG(bpm) AS avg_bpm
     FROM heart_rate_readings
     WHERE user_id = ? AND reading_time >= ? AND reading_time < ?
     GROUP BY bucket_idx ORDER BY bucket_idx"
);
$seriesStmt->execute([$dayStart, $userId, $dayStart, $dayEnd]);

$series = [];
foreach ($seriesStmt as $row) {
    $series[] = [
        'minute' => (int) $row['bucket_idx'] * 10,
        'avg_bpm' => round((float) $row['avg_bpm'], 1),
    ];
}

// Minutes since local midnight, clipped to [0, 1440] so a session that
// starts the evening before (sleep) or runs past midnight still overlays
// cleanly on this single day's 0-1440 chart axis.
function minutesSinceDayStart(string $utcDateTime, string $utcDayStart): float
{
    $seconds = strtotime($utcDateTime) - strtotime($utcDayStart);
    return max(0, min(1440, $seconds / 60));
}

$exerciseStmt = $pdo->prepare(
    "SELECT es.start_time, es.end_time, es.activity_name, at.name AS activity_type
     FROM exercise_sessions es
     LEFT JOIN lut_activity_type at ON at.id = es.activity_type_id
     WHERE es.user_id = ? AND es.start_time < ? AND (es.end_time IS NULL OR es.end_time > ?)"
);
$exerciseStmt->execute([$userId, $dayEnd, $dayStart]);
$exercisePeriods = [];
foreach ($exerciseStmt as $row) {
    $endTime = $row['end_time'] ?? $row['start_time'];
    $exercisePeriods[] = [
        'start_minute' => minutesSinceDayStart($row['start_time'], $dayStart),
        'end_minute' => minutesSinceDayStart($endTime, $dayStart),
        'label' => $row['activity_name'] ?? $row['activity_type'] ?? 'Exercise',
    ];
}

$sleepStmt = $pdo->prepare(
    "SELECT start_time, end_time FROM sleep_sessions
     WHERE user_id = ? AND start_time < ? AND end_time > ?"
);
$sleepStmt->execute([$userId, $dayEnd, $dayStart]);
$sleepPeriods = [];
foreach ($sleepStmt as $row) {
    $sleepPeriods[] = [
        'start_minute' => minutesSinceDayStart($row['start_time'], $dayStart),
        'end_minute' => minutesSinceDayStart($row['end_time'], $dayStart),
        'label' => 'Sleep',
    ];
}

echo json_encode([
    'date' => $localDate,
    'summary' => [
        'min_bpm' => $summary['n'] > 0 ? (int) $summary['min_bpm'] : null,
        'max_bpm' => $summary['n'] > 0 ? (int) $summary['max_bpm'] : null,
        'avg_bpm' => $summary['n'] > 0 ? round((float) $summary['avg_bpm'], 1) : null,
        'resting_bpm' => $restingBpm !== false ? (int) $restingBpm : null,
        'avg_hrv_ms' => $avgHrv !== null ? round((float) $avgHrv, 1) : null,
        'reading_count' => (int) $summary['n'],
    ],
    'series' => $series,
    'exercise_periods' => $exercisePeriods,
    'sleep_periods' => $sleepPeriods,
]);

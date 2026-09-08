<?php

declare(strict_types=1);

// GET /api/heart-rate.php?user_id=2&date=YYYY-MM-DD
// Summary stats (min/max/avg bpm, resting HR, avg HRV) plus a chart-ready
// series bucketed into 10-minute averages — raw per-reading data can run
// into the tens of thousands of rows/day, too dense to chart directly.

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

$tz = new DateTimeZone(Env::get('APP_TIMEZONE', 'UTC'));
$dayStartLocal = (new DateTimeImmutable($dayStart, new DateTimeZone('UTC')))->setTimezone($tz);

$series = [];
foreach ($seriesStmt as $row) {
    $bucketTime = $dayStartLocal->modify('+' . ((int) $row['bucket_idx'] * 10) . ' minutes');
    $series[] = [
        'time' => $bucketTime->format('H:i'),
        'avg_bpm' => round((float) $row['avg_bpm'], 1),
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
]);

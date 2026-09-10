<?php

declare(strict_types=1);

// GET /api/heart-rate-range.php?user_id=2&start=2026-09-09 08:51:00&end=2026-09-09 09:28:00
// Raw (unbucketed) bpm readings between two exact UTC datetimes - used for
// the session-heart-rate popup (Exercise/Heart Rate pages), not a
// calendar-day view like heart-rate.php. A session is minutes to a couple
// hours, so raw readings stay in the hundreds - no need for the 10-minute
// bucketing heart-rate.php uses for a whole day's worth of data.

require_once __DIR__ . '/../../src/Env.php';
require_once __DIR__ . '/../../src/Database.php';

Env::load(__DIR__ . '/../../.env');
header('Content-Type: application/json');

$userId = isset($_GET['user_id']) ? (int) $_GET['user_id'] : 0;
if ($userId <= 0) {
    http_response_code(400);
    echo json_encode(['error' => 'user_id is required']);
    exit;
}

$start = $_GET['start'] ?? null;
$end = $_GET['end'] ?? null;
if ($start === null || $end === null) {
    http_response_code(400);
    echo json_encode(['error' => 'start and end are required']);
    exit;
}

try {
    $startDt = new DateTimeImmutable($start, new DateTimeZone('UTC'));
    $endDt = new DateTimeImmutable($end, new DateTimeZone('UTC'));
} catch (Exception $e) {
    http_response_code(400);
    echo json_encode(['error' => 'invalid start/end']);
    exit;
}
if ($endDt <= $startDt) {
    http_response_code(400);
    echo json_encode(['error' => 'end must be after start']);
    exit;
}

$pdo = Database::connect();

$stmt = $pdo->prepare(
    'SELECT reading_time, bpm FROM heart_rate_readings
     WHERE user_id = ? AND reading_time >= ? AND reading_time < ?
     ORDER BY reading_time'
);
$stmt->execute([$userId, $startDt->format('Y-m-d H:i:s'), $endDt->format('Y-m-d H:i:s')]);

$readings = [];
foreach ($stmt as $row) {
    $readings[] = ['reading_time' => $row['reading_time'], 'bpm' => (int) $row['bpm']];
}

echo json_encode([
    'start' => $startDt->format('Y-m-d H:i:s'),
    'end' => $endDt->format('Y-m-d H:i:s'),
    'readings' => $readings,
]);

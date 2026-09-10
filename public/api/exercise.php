<?php

declare(strict_types=1);

// GET /api/exercise.php?user_id=2&date=YYYY-MM-DD&view=day|week|month|year|custom&end_date=YYYY-MM-DD
// Exercise sessions starting on the requested local day/range. view
// defaults to "day"; end_date is only used, and required, for view=custom.

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
    [$startDate, $endDate, $dayStart, $dayEnd] = LocalDay::resolveRange($timezone, $view, $_GET['date'] ?? null, $_GET['end_date'] ?? null);
} catch (Exception $e) {
    http_response_code(400);
    echo json_encode(['error' => 'invalid date']);
    exit;
}

$pdo = Database::connect();
$stmt = $pdo->prepare(
    "SELECT es.id, es.start_time, es.end_time, es.activity_name, at.name AS activity_type,
            es.duration_ms, es.active_duration_ms, es.calories, es.distance, uc.name AS distance_unit,
            es.steps, es.average_heart_rate, es.has_gps
     FROM exercise_sessions es
     LEFT JOIN lut_activity_type at ON at.id = es.activity_type_id
     LEFT JOIN unit_conversions uc ON uc.id = es.distance_unit_id
     WHERE es.user_id = ? AND es.start_time >= ? AND es.start_time < ?
     ORDER BY es.start_time"
);
$stmt->execute([$userId, $dayStart, $dayEnd]);

$sessionsByDate = [];
foreach ($stmt as $row) {
    $localDate = LocalDay::toLocalDate($timezone, $row['start_time']);
    $sessionsByDate[$localDate][] = [
        'id' => (int) $row['id'],
        'start_time' => $row['start_time'],
        'end_time' => $row['end_time'],
        'activity_name' => $row['activity_name'],
        'activity_type' => $row['activity_type'],
        'duration_minutes' => $row['duration_ms'] !== null ? (int) round(((int) $row['duration_ms']) / 60000) : null,
        'active_duration_minutes' => $row['active_duration_ms'] !== null ? (int) round(((int) $row['active_duration_ms']) / 60000) : null,
        'calories' => $row['calories'] !== null ? (int) $row['calories'] : null,
        'distance' => $row['distance'] !== null ? round((float) $row['distance'], 2) : null,
        'distance_unit' => $row['distance_unit'],
        'steps' => $row['steps'] !== null ? (int) $row['steps'] : null,
        'average_heart_rate' => $row['average_heart_rate'] !== null ? (int) $row['average_heart_rate'] : null,
        'has_gps' => (bool) $row['has_gps'],
    ];
}

$days = [];
foreach ($sessionsByDate as $localDate => $sessions) {
    $days[] = ['date' => $localDate, 'sessions' => $sessions];
}

echo json_encode([
    'view' => $view,
    'start_date' => $startDate,
    'end_date' => $endDate,
    'days' => $days,
]);

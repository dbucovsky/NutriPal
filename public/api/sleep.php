<?php

declare(strict_types=1);

// GET /api/sleep.php?user_id=2&date=YYYY-MM-DD&view=day|week|month|year|custom&end_date=YYYY-MM-DD
// Returns the sleep session(s) that ENDED on the requested local day/range
// (the "woke up on this day" convention most health apps use — a session
// starting the evening before is shown on the morning it ends, not the
// evening it started), each with a per-stage duration breakdown. view
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

$sessionsStmt = $pdo->prepare(
    "SELECT ss.id, ss.start_time, ss.end_time, ss.main_sleep, st.name AS sleep_type
     FROM sleep_sessions ss
     LEFT JOIN lut_sleep_type st ON st.id = ss.sleep_type_id
     WHERE ss.user_id = ? AND ss.end_time >= ? AND ss.end_time < ?
     ORDER BY ss.start_time"
);
$sessionsStmt->execute([$userId, $dayStart, $dayEnd]);
$sessionRows = $sessionsStmt->fetchAll(PDO::FETCH_ASSOC);

// Individual segments in chronological order — NOT grouped/summed by
// stage type. A real night cycles through stages many times (light ->
// deep -> light -> rem -> ...), so summing "all LIGHT time" into one
// bucket would discard that real sequence; the frontend renders these
// in order to show the actual progression through the night, and
// separately totals them per type for the legend.
$stageStmt = $pdo->prepare(
    "SELECT stt.name AS stage_type, ss.start_time, ss.end_time
     FROM sleep_stages ss
     JOIN lut_sleep_stage_type stt ON stt.id = ss.stage_type_id
     WHERE ss.sleep_session_id = ?
     ORDER BY ss.start_time"
);

$sessionsByDate = [];
foreach ($sessionRows as $row) {
    $durationMinutes = (int) round((strtotime($row['end_time']) - strtotime($row['start_time'])) / 60);

    $stageStmt->execute([$row['id']]);
    $stages = [];
    $totalsByType = [];
    foreach ($stageStmt as $stageRow) {
        $minutes = (int) round((strtotime($stageRow['end_time']) - strtotime($stageRow['start_time'])) / 60);
        $stages[] = [
            'stage_type' => $stageRow['stage_type'],
            'start_time' => $stageRow['start_time'],
            'end_time' => $stageRow['end_time'],
            'minutes' => $minutes,
        ];
        $totalsByType[$stageRow['stage_type']] = ($totalsByType[$stageRow['stage_type']] ?? 0) + $minutes;
    }
    $stageTotals = [];
    foreach ($totalsByType as $stageType => $minutes) {
        $stageTotals[] = ['stage_type' => $stageType, 'minutes' => $minutes];
    }

    $localDate = LocalDay::toLocalDate($timezone, $row['end_time']);
    $sessionsByDate[$localDate][] = [
        'id' => (int) $row['id'],
        'start_time' => $row['start_time'],
        'end_time' => $row['end_time'],
        'duration_minutes' => $durationMinutes,
        'sleep_type' => $row['sleep_type'],
        'main_sleep' => $row['main_sleep'] !== null ? (bool) $row['main_sleep'] : null,
        'stages' => $stages,
        'stage_totals' => $stageTotals,
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

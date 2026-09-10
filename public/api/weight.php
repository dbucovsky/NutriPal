<?php

declare(strict_types=1);

// GET /api/weight.php?user_id=2&date=YYYY-MM-DD&view=day|week|month|year|custom&end_date=YYYY-MM-DD
// Weight readings (lut_measurement_type 'weight') for the requested local
// day/range. view defaults to "day"; end_date is only used, and required,
// for view=custom. Stored value/unit are converted to pounds here (rather
// than trusting a hardcoded gram->lb constant) via unit_conversions'
// factor_to_base for both the reading's own unit and the 'pound' row.

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

$poundFactor = (float) $pdo->query("SELECT factor_to_base FROM unit_conversions WHERE name = 'pound'")->fetchColumn();

$stmt = $pdo->prepare(
    "SELECT m.id, m.reading_time, m.value, uc.factor_to_base
     FROM measurements m
     JOIN lut_measurement_type mt ON mt.id = m.measurement_type_id
     JOIN unit_conversions uc ON uc.id = m.unit_id
     WHERE m.user_id = ? AND mt.name = 'weight' AND m.reading_time >= ? AND m.reading_time < ?
     ORDER BY m.reading_time"
);
$stmt->execute([$userId, $dayStart, $dayEnd]);

$readingsByDate = [];
foreach ($stmt as $row) {
    $grams = (float) $row['value'] * (float) $row['factor_to_base'];
    $localDate = LocalDay::toLocalDate($timezone, $row['reading_time']);
    $readingsByDate[$localDate][] = [
        'id' => (int) $row['id'],
        'reading_time' => $row['reading_time'],
        'value_g' => round($grams, 1),
        'value_lb' => round($grams / $poundFactor, 1),
    ];
}

$days = [];
foreach ($readingsByDate as $localDate => $readings) {
    $days[] = ['date' => $localDate, 'readings' => $readings];
}

echo json_encode([
    'view' => $view,
    'start_date' => $startDate,
    'end_date' => $endDate,
    'days' => $days,
]);

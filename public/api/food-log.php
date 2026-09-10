<?php

declare(strict_types=1);

// GET /api/food-log.php?user_id=2&date=YYYY-MM-DD&view=day|week|month|year|custom&end_date=YYYY-MM-DD
// date defaults to "today" in APP_TIMEZONE (not UTC), view defaults to
// "day" (end_date is only used, and required, for view=custom). No
// authorization check on user_id — matches every other still-single-user
// script in this project; real auth is future work.

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
    // lsu.label is an internal technical key (e.g. "api_951_gram",
    // "hc_reported_serving_266") - never meant for display. The real
    // human-readable unit name is unit_conversions.name for a standard
    // unit ("gram") or foods_db_custom_units.unit_name for a per-food
    // custom one ("fl oz", "scoop", "reported serving").
    "SELECT fle.id, fle.start_time, fd.name, fd.brand_name, fle.serving_amount,
            COALESCE(uc.name, fdcu.unit_name) AS serving_unit_label,
            mt.name AS meal_type,
            COALESCE(uc.factor_to_base, fdcu.equivalent_amount) AS unit_amount,
            fd.energy_kcal, fd.total_protein_g, fd.total_carbohydrate_g, fd.total_fat_g
     FROM food_log_entries fle
     JOIN foods_db fd ON fd.id = fle.food_id
     JOIN lut_meal_type mt ON mt.id = fle.meal_type_id
     JOIN lut_serving_unit lsu ON lsu.id = fle.serving_unit_id
     LEFT JOIN unit_conversions uc ON uc.id = lsu.unit_conversion_id
     LEFT JOIN foods_db_custom_units fdcu ON fdcu.id = lsu.foods_db_custom_unit_id
     WHERE fle.user_id = ? AND fle.start_time >= ? AND fle.start_time < ?
     ORDER BY fle.start_time"
);
$stmt->execute([$userId, $dayStart, $dayEnd]);

$scaleValue = static function (?string $per100, float $scale): ?float {
    return $per100 === null ? null : round(((float) $per100) * $scale, 2);
};

$MEAL_KEYS = ['BREAKFAST', 'LUNCH', 'DINNER', 'SNACK', 'ANYTIME'];
$dayBuckets = [];

foreach ($stmt as $row) {
    $unitAmount = $row['unit_amount'] !== null ? (float) $row['unit_amount'] : null;
    $scale = $unitAmount !== null ? ((float) $row['serving_amount'] * $unitAmount) / 100 : null;

    $entry = [
        'id' => (int) $row['id'],
        'name' => $row['name'],
        'brand_name' => $row['brand_name'],
        'serving_amount' => (float) $row['serving_amount'],
        'serving_unit_label' => $row['serving_unit_label'],
        'energy_kcal' => $scale !== null ? $scaleValue($row['energy_kcal'], $scale) : null,
        'protein_g' => $scale !== null ? $scaleValue($row['total_protein_g'], $scale) : null,
        'carb_g' => $scale !== null ? $scaleValue($row['total_carbohydrate_g'], $scale) : null,
        'fat_g' => $scale !== null ? $scaleValue($row['total_fat_g'], $scale) : null,
    ];

    $localDate = LocalDay::toLocalDate($timezone, $row['start_time']);
    if (!isset($dayBuckets[$localDate])) {
        $dayBuckets[$localDate] = [
            'meals' => array_fill_keys($MEAL_KEYS, []),
            'totals' => ['energy_kcal' => 0.0, 'protein_g' => 0.0, 'carb_g' => 0.0, 'fat_g' => 0.0],
        ];
    }

    // lut_meal_type has more values than the 5 main buckets shown here
    // (BEFORE_BREAKFAST, BEFORE_LUNCH, BEFORE_DINNER, AFTER_DINNER) — fold
    // those into ANYTIME for this simple first view rather than adding
    // sparse extra sections.
    $mealType = in_array($row['meal_type'], $MEAL_KEYS, true) ? $row['meal_type'] : 'ANYTIME';
    $dayBuckets[$localDate]['meals'][$mealType][] = $entry;

    foreach (['energy_kcal', 'protein_g', 'carb_g', 'fat_g'] as $key) {
        if ($entry[$key] !== null) {
            $dayBuckets[$localDate]['totals'][$key] += $entry[$key];
        }
    }
}

$days = [];
foreach ($dayBuckets as $localDate => $bucket) {
    foreach ($bucket['totals'] as $key => $value) {
        $bucket['totals'][$key] = round($value, 2);
    }
    $days[] = [
        'date' => $localDate,
        'meals' => array_filter($bucket['meals'], fn($rows) => !empty($rows)),
        'totals' => $bucket['totals'],
    ];
}

echo json_encode([
    'view' => $view,
    'start_date' => $startDate,
    'end_date' => $endDate,
    'days' => $days,
]);

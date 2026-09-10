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

const CORE_MEALS = ['BREAKFAST', 'LUNCH', 'DINNER'];
const MEAL_KEYS = ['BREAKFAST', 'LUNCH', 'DINNER', 'EARLY_SNACK', 'MORNING_SNACK', 'AFTERNOON_SNACK', 'LATE_NIGHT_SNACK'];

// Pass 1: collect every entry per local day (keeping its own meal_type and
// start_time) and accumulate day totals - unchanged from before.
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
        'start_time' => $row['start_time'],
        'energy_kcal' => $scale !== null ? $scaleValue($row['energy_kcal'], $scale) : null,
        'protein_g' => $scale !== null ? $scaleValue($row['total_protein_g'], $scale) : null,
        'carb_g' => $scale !== null ? $scaleValue($row['total_carbohydrate_g'], $scale) : null,
        'fat_g' => $scale !== null ? $scaleValue($row['total_fat_g'], $scale) : null,
    ];

    $localDate = LocalDay::toLocalDate($timezone, $row['start_time']);
    if (!isset($dayBuckets[$localDate])) {
        $dayBuckets[$localDate] = [
            'rawRows' => [],
            'totals' => ['energy_kcal' => 0.0, 'protein_g' => 0.0, 'carb_g' => 0.0, 'fat_g' => 0.0],
        ];
    }

    $dayBuckets[$localDate]['rawRows'][] = ['entry' => $entry, 'meal_type' => $row['meal_type']];

    foreach (['energy_kcal', 'protein_g', 'carb_g', 'fat_g'] as $key) {
        if ($entry[$key] !== null) {
            $dayBuckets[$localDate]['totals'][$key] += $entry[$key];
        }
    }
}

// Pass 2: bucket every non-core-meal entry (whatever the source itself
// called it - SNACK, ANYTIME, BEFORE_LUNCH, BEFORE_DINNER, AFTER_DINNER,
// or anything else) by comparing ITS OWN timestamp against THIS DAY'S real
// Breakfast/Lunch/Dinner start times - not the source's own label, which
// is a fixed clock-window guess, not relative to what this specific day's
// meals actually were. Cascades past any missing reference point (e.g. no
// breakfast logged that day) to the next one instead of leaving a gap.
$days = [];
foreach ($dayBuckets as $localDate => $bucket) {
    $referenceStart = ['BREAKFAST' => null, 'LUNCH' => null, 'DINNER' => null];
    foreach ($bucket['rawRows'] as $row) {
        if (in_array($row['meal_type'], CORE_MEALS, true)) {
            $mealType = $row['meal_type'];
            $startTime = $row['entry']['start_time'];
            if ($referenceStart[$mealType] === null || $startTime < $referenceStart[$mealType]) {
                $referenceStart[$mealType] = $startTime;
            }
        }
    }

    $meals = array_fill_keys(MEAL_KEYS, []);
    foreach ($bucket['rawRows'] as $row) {
        $mealType = $row['meal_type'];
        if (!in_array($mealType, CORE_MEALS, true)) {
            $startTime = $row['entry']['start_time'];
            if ($referenceStart['BREAKFAST'] !== null && $startTime < $referenceStart['BREAKFAST']) {
                $mealType = 'EARLY_SNACK';
            } elseif ($referenceStart['LUNCH'] !== null && $startTime < $referenceStart['LUNCH']) {
                $mealType = 'MORNING_SNACK';
            } elseif ($referenceStart['DINNER'] !== null && $startTime < $referenceStart['DINNER']) {
                $mealType = 'AFTERNOON_SNACK';
            } else {
                $mealType = 'LATE_NIGHT_SNACK';
            }
        }
        $meals[$mealType][] = $row['entry'];
    }

    $totals = $bucket['totals'];
    foreach ($totals as $key => $value) {
        $totals[$key] = round($value, 2);
    }

    $days[] = [
        'date' => $localDate,
        'meals' => array_filter($meals, fn($rows) => !empty($rows)),
        'totals' => $totals,
    ];
}

echo json_encode([
    'view' => $view,
    'start_date' => $startDate,
    'end_date' => $endDate,
    'days' => $days,
]);

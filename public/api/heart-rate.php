<?php

declare(strict_types=1);

// GET /api/heart-rate.php?user_id=2&date=YYYY-MM-DD&view=day|week|month|year|custom&end_date=YYYY-MM-DD
// Per local day in the requested range: summary stats (min/max/avg bpm,
// resting HR, avg HRV) plus a chart-ready series bucketed into 10-minute
// averages — raw per-reading data can run into the tens of thousands of
// rows/day, too dense to chart directly. Also returns exercise/sleep
// periods that OVERLAP that day at all (not just ones that start/end on
// it, unlike exercise.php/sleep.php's own day-assignment rules) so the
// frontend can overlay them on the same minute-of-day timeline as the bpm
// chart. view defaults to "day"; end_date is only used, and required, for
// view=custom.
//
// Per-day boundaries still have to be computed one calendar day at a time
// in PHP (LocalDay::resolveRange('day', ...) per day) to stay DST-correct
// - this project deliberately never trusts MySQL's own timezone
// conversion for that (see LocalDay.php), and America/New_York's DST
// transition days aren't exactly 24h. But running a SEPARATE query per
// day for the summary/HRV aggregates was confirmed directly to cost ~14s
// for a real year view (365 days x 5 queries - each individual query was
// fast, but 1800+ sequential round-trips wasn't) - fixed by batching every
// day's boundaries into one UNION ALL "buckets" subquery and JOINing it
// against the readings table ONCE per aggregate, grouped by day, so the
// whole range is one query no matter how many days it covers. Resting HR
// and the exercise/sleep overlays are similarly fetched once for the
// whole range and split per day in PHP (all three source tables are small
// enough - unlike heart_rate_readings - that this is cheap).
//
// The bpm-curve series itself stays genuinely one query per day (skipped
// entirely past $MAX_SERIES_DAYS) - it's the one thing that can't be
// batched the same way since each day's buckets are relative to that
// day's own local midnight, and month/year views render every day
// collapsed by default anyway (see MultiDay.jsx) so that chart is never
// seen there without first expanding a day.

require_once __DIR__ . '/../../src/Env.php';
require_once __DIR__ . '/../../src/Database.php';
require_once __DIR__ . '/../../src/LocalDay.php';
require_once __DIR__ . '/../../src/MaxHeartRate.php';

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
    [$startDate, $endDate, $rangeUtcStart, $rangeUtcEnd] = LocalDay::resolveRange(
        $timezone, $view, $_GET['date'] ?? null, $_GET['end_date'] ?? null
    );
} catch (Exception $e) {
    http_response_code(400);
    echo json_encode(['error' => 'invalid date']);
    exit;
}

$pdo = Database::connect();

// [localDate, utcDayStart, utcDayEnd] per calendar day in the range, in order.
$dayBounds = [];
$cursor = new DateTimeImmutable($startDate);
$last = new DateTimeImmutable($endDate);
while ($cursor <= $last) {
    $localDate = $cursor->format('Y-m-d');
    [, , $dayStart, $dayEnd] = LocalDay::resolveRange($timezone, 'day', $localDate, null);
    $dayBounds[] = [$localDate, $dayStart, $dayEnd];
    $cursor = $cursor->modify('+1 day');
}

const MAX_SERIES_DAYS = 10;
$includeSeries = count($dayBounds) <= MAX_SERIES_DAYS;

// Batches one independent aggregate subquery per calendar day into a
// single UNION ALL statement - each subquery keeps its own simple
// `WHERE user_id = ? AND reading_time >= ? AND reading_time < ?` range
// (still hits the (user_id, reading_time) index exactly like the original
// per-day query did), so this is the same per-day query cost as before,
// just merged into ONE network round trip instead of N. (A first attempt
// at batching this via a day-boundaries-derived-table JOIN looked cleaner
// but made MySQL evaluate every reading row against every day's bounds
// with no index - confirmed directly to hang for 2+ minutes on a year
// range before being killed. UNION ALL of independent queries avoids that
// failure mode entirely since each branch is optimized on its own.)
function unionAllPerDay(string $table, string $selectExpr, array $dayBounds, int $userId, array &$params): string
{
    $parts = [];
    foreach ($dayBounds as $i => [, $dayStart, $dayEnd]) {
        $parts[] = "SELECT {$i} AS day_idx, {$selectExpr} FROM {$table} WHERE user_id = ? AND reading_time >= ? AND reading_time < ?";
        $params[] = $userId;
        $params[] = $dayStart;
        $params[] = $dayEnd;
    }
    return implode(' UNION ALL ', $parts);
}

$bpmParams = [];
$bpmSql = unionAllPerDay(
    'heart_rate_readings',
    'MIN(bpm) AS min_bpm, MAX(bpm) AS max_bpm, AVG(bpm) AS avg_bpm, COUNT(*) AS n',
    $dayBounds, $userId, $bpmParams
);
$bpmStmt = $pdo->prepare($bpmSql);
$bpmStmt->execute($bpmParams);
$bpmByIdx = [];
foreach ($bpmStmt as $row) {
    $bpmByIdx[(int) $row['day_idx']] = $row;
}

$hrvParams = [];
$hrvSql = unionAllPerDay('heart_rate_variability_readings', 'AVG(rmssd_ms) AS avg_hrv', $dayBounds, $userId, $hrvParams);
$hrvStmt = $pdo->prepare($hrvSql);
$hrvStmt->execute($hrvParams);
$hrvByIdx = [];
foreach ($hrvStmt as $row) {
    $hrvByIdx[(int) $row['day_idx']] = $row['avg_hrv'];
}

$restingStmt = $pdo->prepare(
    'SELECT reading_date, bpm FROM daily_resting_heart_rate WHERE user_id = ? AND reading_date BETWEEN ? AND ?'
);
$restingStmt->execute([$userId, $startDate, $endDate]);
$restingByDate = [];
foreach ($restingStmt as $row) {
    $restingByDate[$row['reading_date']] = (int) $row['bpm'];
}

$exerciseStmt = $pdo->prepare(
    "SELECT es.id, es.start_time, es.end_time, es.activity_name, at.name AS activity_type
     FROM exercise_sessions es
     LEFT JOIN lut_activity_type at ON at.id = es.activity_type_id
     WHERE es.user_id = ? AND es.start_time < ? AND (es.end_time IS NULL OR es.end_time > ?)"
);
$exerciseStmt->execute([$userId, $rangeUtcEnd, $rangeUtcStart]);
$allExercise = $exerciseStmt->fetchAll(PDO::FETCH_ASSOC);

$sleepStmt = $pdo->prepare(
    "SELECT start_time, end_time FROM sleep_sessions
     WHERE user_id = ? AND start_time < ? AND end_time > ?"
);
$sleepStmt->execute([$userId, $rangeUtcEnd, $rangeUtcStart]);
$allSleep = $sleepStmt->fetchAll(PDO::FETCH_ASSOC);

// Minutes since local midnight, clipped to [0, 1440] so a session that
// starts the evening before (sleep) or runs past midnight still overlays
// cleanly on that single day's 0-1440 chart axis.
function minutesSinceDayStart(string $utcDateTime, string $utcDayStart): float
{
    $seconds = strtotime($utcDateTime) - strtotime($utcDayStart);
    return max(0, min(1440, $seconds / 60));
}

$seriesStmt = null;
if ($includeSeries) {
    // 10-minute buckets, indexed by seconds-since-day-start / 600 — dense
    // enough for a smooth day-shaped line, sparse enough to chart
    // instantly regardless of how many raw readings were reported.
    $seriesStmt = $pdo->prepare(
        "SELECT FLOOR(TIMESTAMPDIFF(SECOND, ?, reading_time) / 600) AS bucket_idx, AVG(bpm) AS avg_bpm
         FROM heart_rate_readings
         WHERE user_id = ? AND reading_time >= ? AND reading_time < ?
         GROUP BY bucket_idx ORDER BY bucket_idx"
    );
}

$days = [];
foreach ($dayBounds as $i => [$localDate, $dayStart, $dayEnd]) {
    $bpmRow = $bpmByIdx[$i] ?? null;
    $readingCount = $bpmRow !== null ? (int) $bpmRow['n'] : 0;

    $exercisePeriods = [];
    foreach ($allExercise as $row) {
        if ($row['start_time'] >= $dayEnd || ($row['end_time'] !== null && $row['end_time'] <= $dayStart)) {
            continue;
        }
        $endTime = $row['end_time'] ?? $row['start_time'];
        $exercisePeriods[] = [
            'id' => (int) $row['id'],
            'start_minute' => minutesSinceDayStart($row['start_time'], $dayStart),
            'end_minute' => minutesSinceDayStart($endTime, $dayStart),
            'label' => $row['activity_name'] ?? $row['activity_type'] ?? 'Exercise',
            'start_time' => $row['start_time'],
            'end_time' => $endTime,
        ];
    }

    $sleepPeriods = [];
    foreach ($allSleep as $row) {
        if ($row['start_time'] >= $dayEnd || $row['end_time'] <= $dayStart) {
            continue;
        }
        $sleepPeriods[] = [
            'start_minute' => minutesSinceDayStart($row['start_time'], $dayStart),
            'end_minute' => minutesSinceDayStart($row['end_time'], $dayStart),
            'label' => 'Sleep',
        ];
    }

    if ($readingCount === 0 && count($exercisePeriods) === 0 && count($sleepPeriods) === 0) {
        continue;
    }

    $series = [];
    if ($includeSeries) {
        $seriesStmt->execute([$dayStart, $userId, $dayStart, $dayEnd]);
        foreach ($seriesStmt as $row) {
            $series[] = [
                'minute' => (int) $row['bucket_idx'] * 10,
                'avg_bpm' => round((float) $row['avg_bpm'], 1),
            ];
        }
    }

    $avgHrv = $hrvByIdx[$i] ?? null;

    $days[] = [
        'date' => $localDate,
        'summary' => [
            'min_bpm' => $readingCount > 0 ? (int) $bpmRow['min_bpm'] : null,
            'max_bpm' => $readingCount > 0 ? (int) $bpmRow['max_bpm'] : null,
            'avg_bpm' => $readingCount > 0 ? round((float) $bpmRow['avg_bpm'], 1) : null,
            'resting_bpm' => $restingByDate[$localDate] ?? null,
            'avg_hrv_ms' => $avgHrv !== null ? round((float) $avgHrv, 1) : null,
            'reading_count' => $readingCount,
        ],
        'series' => $series,
        'exercise_periods' => $exercisePeriods,
        'sleep_periods' => $sleepPeriods,
    ];
}

// Max HR is only needed here for zone-coloring the exercise-session popup
// chart (clicking a shaded band on this page's own day chart) - resolved
// per-day, as of that specific date, the same historically-accurate way
// exercise.php does it (see src/MaxHeartRate.php). Only computed for days
// that actually have an exercise period, since most days here won't.
$datesNeedingMaxHr = [];
foreach ($days as $day) {
    if ($day['exercise_periods'] !== []) {
        $datesNeedingMaxHr[] = $day['date'];
    }
}
$maxHrByDate = MaxHeartRate::getEffectiveForDates($pdo, $userId, $datesNeedingMaxHr, $timezone);
foreach ($days as &$day) {
    $day['max_heart_rate'] = $maxHrByDate[$day['date']]['value'] ?? null;
}
unset($day);

echo json_encode([
    'view' => $view,
    'start_date' => $startDate,
    'end_date' => $endDate,
    'series_included' => $includeSeries,
    'days' => $days,
]);

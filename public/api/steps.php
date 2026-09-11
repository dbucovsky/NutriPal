<?php

declare(strict_types=1);

// GET /api/steps.php?user_id=2&date=YYYY-MM-DD&view=day|week|month|year|custom&end_date=YYYY-MM-DD
// Per local day in the requested range: a reconciled step total (see
// below) plus, for short enough ranges, an hourly breakdown for that day's
// own steps chart. view defaults to "day"; end_date is only used, and
// required, for view=custom.
//
// steps_readings has a real, still-open cross-source duplication problem
// (documented in doc/wiki/Database-Schema.md's Open Items): Health Connect
// bulk imports and the live Google Health API sync each independently
// report steps for overlapping real time windows, at different
// reading_times, so summing every row for a day double- or triple-counts.
//
// This does not attempt the full reconciliation that would be needed to fix
// that properly (like the food_log_entries/sleep/exercise/measurements
// cross-source work elsewhere in this project) - that's a bigger, separate
// effort. Instead: the wearable (data_source name "Fitbit" - Health
// Connect's historical import label - or "Charge 5" - the live API's label
// for the exact same physical device) is trusted as the PREFERRED source,
// since it's worn continuously; every other data_source (phone-side:
// "Damian's S22", "HEALTH_CONNECT", "MobileTrack" - Fitbit's own
// phone-fallback feature, not the watch - "Fit", or unattributed) is
// grouped as "Phone". Per local 10-minute window (same granularity
// heart-rate.php already uses for its own chart buckets): use Fitbit's
// count UNLESS it's very low (under LOW_STEPS_THRESHOLD) AND Phone's count
// for that same window is at least RATIO_THRESHOLD times higher - i.e. the
// watch demonstrably failed to track real movement that Phone caught
// instead (wasn't worn, or physically couldn't detect it - e.g. pushing a
// shopping cart suppresses wrist swing). This deliberately does NOT pick
// whichever source is merely slightly ahead in a window (confirmed
// unwanted behavior from an earlier version: Health Connect edging out
// Charge 5 by a few hundred steps in one hour on 2026-09-09 was real
// sensor-to-sensor noise, not a genuine tracking gap, and got "corrected"
// away by this design). `source` is `Fitbit`/`Phone` when every window
// agreed, `Mixed` when some windows fell back and others didn't, or `null`
// when the day has no readings at all. Still a disclosed heuristic, not a
// real fix - see the Known limitations note in CHANGELOG.md.
//
// Every calendar day in the range is represented, even with zero readings
// - a day with no data becomes {steps: 0, source: null}, not simply
// omitted, so a missed-sync day doesn't quietly vanish from an average
// instead of counting against it. This only applies through today: a day
// that hasn't happened yet is left out of the response entirely, not
// fabricated as a zero.

require_once __DIR__ . '/../../src/Env.php';
require_once __DIR__ . '/../../src/Database.php';
require_once __DIR__ . '/../../src/LocalDay.php';
require_once __DIR__ . '/../../src/StepsGoal.php';

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

// The wearable, across both pipelines that have ever reported it - see the
// docblock above for why these two names are the same physical device.
const FITBIT_SOURCE_NAMES = ['Fitbit', 'Charge 5'];

const BUCKET_MINUTES = 10;

// Below this many steps in a window, Fitbit is treated as "not really
// tracking" rather than just genuinely low-activity - tuned so a slow desk
// afternoon doesn't fall back to Phone, but a watch left on a treadmill's
// shelf (or not worn at all) does.
const LOW_STEPS_THRESHOLD = 100;

// Phone must beat Fitbit by at least this multiple in a window before it's
// trusted over it - guards against picking Phone just because it happened
// to edge Fitbit out by ordinary sensor-to-sensor noise.
const RATIO_THRESHOLD = 3.0;

// Same threshold/idea as heart-rate.php's MAX_SERIES_DAYS - a per-day chart
// is only fetched upfront for short ranges; longer ones get it on demand.
const MAX_SERIES_DAYS = 10;

$pdo = Database::connect();

// One calendar day at a time (DST-safe, same approach heart-rate.php uses)
// - stops at today, since a future day isn't a "zero steps" day, it's a
// day that hasn't happened yet and shouldn't appear at all.
$todayLocalDate = (new DateTimeImmutable('now', new DateTimeZone($timezone)))->format('Y-m-d');
$dayBounds = [];
$cursor = new DateTimeImmutable($startDate);
$last = new DateTimeImmutable($endDate);
while ($cursor <= $last) {
    $localDate = $cursor->format('Y-m-d');
    if ($localDate > $todayLocalDate) {
        break;
    }
    $dayBounds[] = $localDate;
    $cursor = $cursor->modify('+1 day');
}

$includeSeries = count($dayBounds) <= MAX_SERIES_DAYS;

$stmt = $pdo->prepare(
    "SELECT sr.reading_time, sr.steps, ds.name AS data_source_name
     FROM steps_readings sr
     LEFT JOIN lut_data_source ds ON ds.id = sr.data_source_id
     WHERE sr.user_id = ? AND sr.reading_time >= ? AND sr.reading_time < ?"
);
$stmt->execute([$userId, $rangeStart, $rangeEnd]);

// Per local day, per 10-minute local-time window: Fitbit's steps and
// Phone's steps (every non-Fitbit source, summed together - the window-
// level decision is Fitbit-vs-Phone, not Fitbit-vs-any-one-other-device).
// Also tracked per day, independent of any window: each side's own naive
// whole-day total, purely for the transparency comparison in the response.
$byDateBucket = [];
$byDateSide = [];
foreach ($stmt as $row) {
    $utc = new DateTimeImmutable($row['reading_time'], new DateTimeZone('UTC'));
    $local = $utc->setTimezone(new DateTimeZone($timezone));
    $localDate = $local->format('Y-m-d');
    if ($localDate > $todayLocalDate) {
        continue;
    }
    $bucketIdx = intdiv(((int) $local->format('H')) * 60 + (int) $local->format('i'), BUCKET_MINUTES);

    $sourceName = $row['data_source_name'] ?? 'Unknown';
    $side = in_array($sourceName, FITBIT_SOURCE_NAMES, true) ? 'fitbit' : 'phone';
    $steps = (int) $row['steps'];

    $byDateBucket[$localDate][$bucketIdx][$side] = ($byDateBucket[$localDate][$bucketIdx][$side] ?? 0) + $steps;
    $byDateSide[$localDate][$side] = ($byDateSide[$localDate][$side] ?? 0) + $steps;
}

$goal = StepsGoal::get($pdo, $userId);

$days = [];
foreach ($dayBounds as $localDate) {
    $buckets = $byDateBucket[$localDate] ?? [];

    $total = 0;
    $usedFitbit = false;
    $usedPhone = false;
    $hourly = array_fill(0, 24, 0);

    foreach ($buckets as $bucketIdx => $b) {
        $fitbitSteps = $b['fitbit'] ?? 0;
        $phoneSteps = $b['phone'] ?? 0;

        $fitbitFailed = $fitbitSteps < LOW_STEPS_THRESHOLD
            && $phoneSteps > $fitbitSteps
            && ($fitbitSteps === 0 || $phoneSteps / $fitbitSteps >= RATIO_THRESHOLD);

        $winning = $fitbitFailed ? $phoneSteps : $fitbitSteps;
        if ($fitbitFailed) {
            $usedPhone = true;
        } else {
            $usedFitbit = true;
        }

        $total += $winning;
        $hourly[intdiv($bucketIdx * BUCKET_MINUTES, 60)] += $winning;
    }

    if ($buckets === []) {
        $source = null;
    } else {
        $source = $usedFitbit && $usedPhone ? 'Mixed' : ($usedPhone ? 'Phone' : 'Fitbit');
    }

    $sideTotals = $byDateSide[$localDate] ?? [];
    $otherSources = [];
    if ($source !== 'Fitbit' && ($sideTotals['fitbit'] ?? 0) > 0) {
        $otherSources[] = ['name' => 'Fitbit', 'steps' => $sideTotals['fitbit']];
    }
    if ($source !== 'Phone' && ($sideTotals['phone'] ?? 0) > 0) {
        $otherSources[] = ['name' => 'Phone', 'steps' => $sideTotals['phone']];
    }

    $days[] = [
        'date' => $localDate,
        'steps' => $total,
        'source' => $source,
        'other_sources' => $otherSources,
        'series' => $includeSeries
            ? array_map(fn (int $hour, int $steps): array => ['hour' => $hour, 'steps' => $steps], array_keys($hourly), $hourly)
            : [],
    ];
}

echo json_encode([
    'view' => $view,
    'start_date' => $startDate,
    'end_date' => $endDate,
    'series_included' => $includeSeries,
    'goal' => $goal,
    'days' => $days,
]);

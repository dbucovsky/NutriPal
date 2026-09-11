<?php

declare(strict_types=1);

require_once __DIR__ . '/LocalDay.php';

/**
 * Max heart rate as three independently-tracked sources - age estimate
 * (220 - age, recomputed lazily on birthday, in max_heart_rate_history),
 * observed-from-sessions (the highest *sustained* bpm during real
 * running/treadmill/aerobics sessions in the last few weeks, divided by
 * 0.95 since even a hard effort rarely reaches literal 100% of true max,
 * stored per-session on exercise_sessions.observed_max_hr_estimate), and a
 * manual override (also in max_heart_rate_history) - plus
 * users.max_hr_source_id saying which one is actually used for zone
 * coloring right now. All three keep being computed regardless of which is
 * active, so switching is instant and never loses the other two.
 *
 * "Sustained" (see sustainedPeakBpm()) means the highest rolling *median*
 * bpm over any 120-second window in the session, not the single highest
 * raw reading - a lone sensor glitch (optical wrist HR sensors do this) can
 * spike one reading far above everything around it, which would otherwise
 * inflate the observed estimate off one bad sample. A median is robust to
 * exactly one outlier inside its window; a genuinely sustained hard effort
 * still surfaces since the whole window is elevated, not just one point.
 *
 * Nothing here runs on a schedule - this app has no cron job. Both the
 * age-estimate's "has a birthday passed?" check and the observed
 * estimate's "has this session's heart-rate data arrived yet?" check
 * happen lazily, on whatever request next asks for the current value.
 *
 * The observed estimate was originally going to be computed "live" the
 * moment a session is inserted during sync, but that turned out not to be
 * reliable: scripts/sync-google-health.php inserts exercise_sessions
 * BEFORE heart_rate_readings in every run (including --full), so the
 * matching heart-rate data usually doesn't exist yet at that exact moment
 * - computing it there would almost always find nothing. Health Connect's
 * importer happens to insert heart rate first, but the two scripts
 * disagree, so insert-time computation can't be made reliable either way.
 * Lazy-on-read (this file's own existing pattern for the age estimate, and
 * heart-rate.php's existing exercise/heart-rate join) sidesteps the
 * ordering question entirely.
 */
final class MaxHeartRate
{
    /** Matched against lut_activity_type.name - "treadmill/runs/aerobics", explicitly not walks or generic workouts. */
    private const QUALIFYING_ACTIVITY_TYPES = ['Running', 'Running (Treadmill)', 'API_RUNNING', 'API_TREADMILL', 'Exercise Class'];

    private const OBSERVED_ESTIMATE_FACTOR = 0.95;

    private const OBSERVED_WINDOW_DAYS = 21;

    /** How long a peak must hold up (as a rolling-median window) to count - see sustainedPeakBpm(). */
    private const SUSTAINED_PEAK_WINDOW_SECONDS = 120;

    /** Below this many readings, a window's median is too easily dominated by one or two points to trust. */
    private const SUSTAINED_PEAK_MIN_READINGS = 3;

    private const SOURCE_NAMES = [1 => 'age', 2 => 'observed', 3 => 'manual'];

    /**
     * All three candidate values plus the resolved "effective" one, for the
     * Settings panel (which shows all three) and exercise.php (which only
     * needs 'effective'/'effective_source').
     *
     * @return array{
     *   age: ?int, observed: ?int, manual: ?int,
     *   source: ?string, effective: ?int, effective_source: ?string
     * }
     */
    public static function getAllEstimates(PDO $pdo, int $userId): array
    {
        $age = self::getAgeEstimate($pdo, $userId);
        $observed = self::getObservedEstimate($pdo, $userId);
        $manual = self::getManualOverride($pdo, $userId);

        $sourceStmt = $pdo->prepare('SELECT max_hr_source_id FROM users WHERE id = ?');
        $sourceStmt->execute([$userId]);
        $sourceId = $sourceStmt->fetchColumn();
        $source = $sourceId !== false && $sourceId !== null ? (self::SOURCE_NAMES[(int) $sourceId] ?? null) : null;

        $candidates = ['age' => $age, 'observed' => $observed, 'manual' => $manual];
        $effectiveSource = $source !== null && $candidates[$source] !== null ? $source : null;
        // The preferred source has nothing yet (e.g. "observed" chosen but
        // no qualifying sessions in the window) - fall back to age, since
        // that's the one source that's available as soon as a birth date
        // is set, rather than leaving the zone coloring with nothing at all.
        if ($effectiveSource === null && $age !== null) {
            $effectiveSource = 'age';
        }

        return [
            'age' => $age,
            'observed' => $observed,
            'manual' => $manual,
            'source' => $source,
            'effective' => $effectiveSource !== null ? $candidates[$effectiveSource] : null,
            'effective_source' => $effectiveSource,
        ];
    }

    /**
     * The historically-accurate effective Max HR for each of $dates, for
     * coloring old exercise sessions against the estimate that was actually
     * true on their own day rather than today's. The *source* preference
     * (age/observed/manual) is always today's users.max_hr_source_id -
     * there's no history of preference changes to consult, so a date before
     * the user ever switched sources still gets classified as if today's
     * choice had always been active, just with that source's own dated
     * value. Age needs no stored history to do this - it's a pure function
     * of birth_date - but manual (a user-entered fact) and observed (a
     * rolling window over real sessions) each need their own dated lookup.
     *
     * @param string[] $dates 'Y-m-d' dates, any order/duplicates
     * @return array<string, array{value: ?int, source: ?string}> keyed by date
     */
    public static function getEffectiveForDates(PDO $pdo, int $userId, array $dates, string $timezone): array
    {
        if ($dates === []) {
            return [];
        }
        $dates = array_values(array_unique($dates));
        sort($dates);

        $userStmt = $pdo->prepare('SELECT birth_date, max_hr_source_id FROM users WHERE id = ?');
        $userStmt->execute([$userId]);
        $user = $userStmt->fetch(PDO::FETCH_ASSOC);
        $birthDate = $user['birth_date'] ?? null;
        $sourceId = $user['max_hr_source_id'] ?? null;
        $source = $sourceId !== null ? (self::SOURCE_NAMES[(int) $sourceId] ?? null) : null;

        $manualHistory = self::manualOverrideHistory($pdo, $userId);
        $observedByDate = self::observedEstimatesForDates($pdo, $userId, $dates, $timezone);

        $result = [];
        foreach ($dates as $date) {
            $age = $birthDate !== null ? self::estimateFromAge((string) $birthDate, $date) : null;
            $manual = self::valueAsOf($manualHistory, $date);
            $observed = $observedByDate[$date] ?? null;

            $candidates = ['age' => $age, 'observed' => $observed, 'manual' => $manual];
            $effectiveSource = $source !== null && $candidates[$source] !== null ? $source : null;
            if ($effectiveSource === null && $age !== null) {
                $effectiveSource = 'age';
            }

            $result[$date] = [
                'value' => $effectiveSource !== null ? $candidates[$effectiveSource] : null,
                'source' => $effectiveSource,
            ];
        }
        return $result;
    }

    public static function setManualOverride(PDO $pdo, int $userId, int $bpm): void
    {
        $today = (new DateTimeImmutable('today'))->format('Y-m-d');
        $stmt = $pdo->prepare(
            'INSERT INTO max_heart_rate_history (user_id, effective_date, bpm, is_manual_override)
             VALUES (?, ?, ?, TRUE)
             ON DUPLICATE KEY UPDATE bpm = VALUES(bpm), is_manual_override = TRUE'
        );
        $stmt->execute([$userId, $today, $bpm]);
    }

    /** @param string $source one of 'age' | 'observed' | 'manual' */
    public static function setSource(PDO $pdo, int $userId, string $source): void
    {
        $id = array_search($source, self::SOURCE_NAMES, true);
        if ($id === false) {
            return;
        }
        $pdo->prepare('UPDATE users SET max_hr_source_id = ? WHERE id = ?')->execute([$id, $userId]);
    }

    /** The 220-age estimate, recomputing and storing a fresh row (in max_heart_rate_history) if a birthday has passed since the last non-override one. */
    private static function getAgeEstimate(PDO $pdo, int $userId): ?int
    {
        $userStmt = $pdo->prepare('SELECT birth_date FROM users WHERE id = ?');
        $userStmt->execute([$userId]);
        $birthDate = $userStmt->fetchColumn();
        if ($birthDate === false || $birthDate === null) {
            return null;
        }

        $latestStmt = $pdo->prepare(
            "SELECT bpm, effective_date FROM max_heart_rate_history
             WHERE user_id = ? AND is_manual_override = FALSE ORDER BY effective_date DESC LIMIT 1"
        );
        $latestStmt->execute([$userId]);
        $latest = $latestStmt->fetch(PDO::FETCH_ASSOC);

        $currentPeriodStart = self::currentBirthdayPeriodStart($birthDate);
        $estimate = self::estimateFromAge($birthDate, $currentPeriodStart);
        if ($estimate === null) {
            // Implausible birth_date (future date, or an age outside any
            // real human range) - don't compute nonsense, fall back to
            // whatever's already stored instead.
            return $latest !== false ? (int) $latest['bpm'] : null;
        }

        if ($latest === false || $latest['effective_date'] < $currentPeriodStart) {
            $insert = $pdo->prepare(
                'INSERT INTO max_heart_rate_history (user_id, effective_date, bpm, is_manual_override)
                 VALUES (?, ?, ?, FALSE)
                 ON DUPLICATE KEY UPDATE bpm = VALUES(bpm), is_manual_override = FALSE'
            );
            $insert->execute([$userId, $currentPeriodStart, $estimate]);
            return $estimate;
        }

        return (int) $latest['bpm'];
    }

    private static function getManualOverride(PDO $pdo, int $userId): ?int
    {
        $stmt = $pdo->prepare(
            'SELECT bpm FROM max_heart_rate_history
             WHERE user_id = ? AND is_manual_override = TRUE ORDER BY effective_date DESC LIMIT 1'
        );
        $stmt->execute([$userId]);
        $bpm = $stmt->fetchColumn();
        return $bpm !== false ? (int) $bpm : null;
    }

    /** Every manual-override row ever set, oldest first - for picking "whichever was in effect on date X" via valueAsOf(). */
    private static function manualOverrideHistory(PDO $pdo, int $userId): array
    {
        $stmt = $pdo->prepare(
            'SELECT bpm, effective_date FROM max_heart_rate_history
             WHERE user_id = ? AND is_manual_override = TRUE ORDER BY effective_date ASC'
        );
        $stmt->execute([$userId]);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    /** Latest of $rows (sorted ascending by effective_date) with effective_date <= $date, or null if $date predates all of them. */
    private static function valueAsOf(array $rows, string $date): ?int
    {
        $value = null;
        foreach ($rows as $row) {
            if ($row['effective_date'] > $date) {
                break;
            }
            $value = (int) $row['bpm'];
        }
        return $value;
    }

    /** Backfills any qualifying session in the window still missing its estimate, then returns the max over that same window. */
    private static function getObservedEstimate(PDO $pdo, int $userId): ?int
    {
        $windowStart = self::windowStart();
        self::backfillObservedEstimatesInRange($pdo, $userId, $windowStart, null);

        $stmt = $pdo->prepare(
            'SELECT MAX(observed_max_hr_estimate) FROM exercise_sessions
             WHERE user_id = ? AND start_time >= ? AND observed_max_hr_estimate IS NOT NULL'
        );
        $stmt->execute([$userId, $windowStart]);
        $max = $stmt->fetchColumn();
        return $max !== false && $max !== null ? (int) $max : null;
    }

    /**
     * The trailing-21-day observed max as of each of $dates (not just
     * today), for historically-accurate zone coloring on old sessions.
     * Backfills every qualifying session across the whole span at once
     * (from 21 days before the earliest requested date through the latest
     * one), then computes each date's own trailing window against that one
     * fetched batch rather than a separate query per date.
     *
     * @param string[] $dates sorted ascending 'Y-m-d'
     * @return array<string, ?int> keyed by date
     */
    private static function observedEstimatesForDates(PDO $pdo, int $userId, array $dates, string $timezone): array
    {
        $earliest = $dates[0];
        $latest = $dates[count($dates) - 1];
        $rangeStart = (new DateTimeImmutable($earliest))->modify('-' . self::OBSERVED_WINDOW_DAYS . ' days')->format('Y-m-d H:i:s');
        $rangeEnd = (new DateTimeImmutable($latest))->modify('+1 day')->format('Y-m-d H:i:s');

        self::backfillObservedEstimatesInRange($pdo, $userId, $rangeStart, $rangeEnd);

        $placeholders = implode(',', array_fill(0, count(self::QUALIFYING_ACTIVITY_TYPES), '?'));
        $stmt = $pdo->prepare(
            "SELECT es.start_time, es.observed_max_hr_estimate
             FROM exercise_sessions es
             JOIN lut_activity_type at ON at.id = es.activity_type_id
             WHERE es.user_id = ? AND es.start_time >= ? AND es.start_time < ?
             AND at.name IN ($placeholders) AND es.observed_max_hr_estimate IS NOT NULL"
        );
        $stmt->execute([$userId, $rangeStart, $rangeEnd, ...self::QUALIFYING_ACTIVITY_TYPES]);

        $sessionsByDate = [];
        foreach ($stmt as $row) {
            $sessionsByDate[] = [
                'date' => LocalDay::toLocalDate($timezone, $row['start_time']),
                'value' => (int) $row['observed_max_hr_estimate'],
            ];
        }

        $result = [];
        foreach ($dates as $date) {
            $windowFrom = (new DateTimeImmutable($date))->modify('-' . self::OBSERVED_WINDOW_DAYS . ' days')->format('Y-m-d');
            $max = null;
            foreach ($sessionsByDate as $session) {
                if ($session['date'] >= $windowFrom && $session['date'] <= $date) {
                    $max = $max === null ? $session['value'] : max($max, $session['value']);
                }
            }
            $result[$date] = $max;
        }
        return $result;
    }

    /**
     * Finds qualifying sessions in [$rangeStart, $rangeEnd) with no stored
     * estimate yet and fills them in from heart_rate_readings, if that data
     * exists now. A null $rangeEnd means no upper bound. Self-limiting: a
     * session that never gets heart-rate data simply stops being checked
     * once it's outside whatever range is next requested - no permanent
     * dead weight.
     */
    private static function backfillObservedEstimatesInRange(PDO $pdo, int $userId, string $rangeStart, ?string $rangeEnd): void
    {
        $placeholders = implode(',', array_fill(0, count(self::QUALIFYING_ACTIVITY_TYPES), '?'));
        $sql = "SELECT es.id, es.start_time, es.end_time
                FROM exercise_sessions es
                JOIN lut_activity_type at ON at.id = es.activity_type_id
                WHERE es.user_id = ? AND es.start_time >= ? AND es.observed_max_hr_estimate IS NULL
                AND at.name IN ($placeholders)";
        $params = [$userId, $rangeStart, ...self::QUALIFYING_ACTIVITY_TYPES];
        if ($rangeEnd !== null) {
            $sql .= ' AND es.start_time < ?';
            $params[] = $rangeEnd;
        }

        $sessionsStmt = $pdo->prepare($sql);
        $sessionsStmt->execute($params);
        $sessions = $sessionsStmt->fetchAll(PDO::FETCH_ASSOC);
        if ($sessions === []) {
            return;
        }

        $readingsStmt = $pdo->prepare(
            'SELECT reading_time, bpm FROM heart_rate_readings
             WHERE user_id = ? AND reading_time BETWEEN ? AND ? ORDER BY reading_time'
        );
        $updateStmt = $pdo->prepare('UPDATE exercise_sessions SET observed_max_hr_estimate = ? WHERE id = ?');

        foreach ($sessions as $session) {
            $endTime = $session['end_time'] ?? $session['start_time'];
            $readingsStmt->execute([$userId, $session['start_time'], $endTime]);
            $peak = self::sustainedPeakBpm($readingsStmt->fetchAll(PDO::FETCH_ASSOC));
            if ($peak !== null) {
                $updateStmt->execute([(int) round($peak / self::OBSERVED_ESTIMATE_FACTOR), $session['id']]);
            }
        }
    }

    /**
     * The highest rolling-median bpm over any SUSTAINED_PEAK_WINDOW_SECONDS
     * window in $readings, using each reading's own timestamp (not a fixed
     * sample count) so this works regardless of a device's actual sampling
     * interval. A two-pointer sliding window over time, taking the median
     * of whatever readings currently fall inside it; windows with fewer
     * than SUSTAINED_PEAK_MIN_READINGS are skipped (too little data to
     * trust a median from, mainly an edge case at the very start of the
     * session before 120s of history has accumulated).
     *
     * @param array<array{reading_time: string, bpm: int|string}> $readings sorted ascending by reading_time
     */
    private static function sustainedPeakBpm(array $readings): ?int
    {
        $n = count($readings);
        if ($n === 0) {
            return null;
        }

        $times = array_map(static fn (array $r): int => strtotime((string) $r['reading_time']), $readings);
        $bpms = array_map(static fn (array $r): int => (int) $r['bpm'], $readings);

        $best = null;
        $left = 0;
        for ($right = 0; $right < $n; $right++) {
            while ($times[$right] - $times[$left] > self::SUSTAINED_PEAK_WINDOW_SECONDS) {
                $left++;
            }
            $windowSize = $right - $left + 1;
            if ($windowSize < self::SUSTAINED_PEAK_MIN_READINGS) {
                continue;
            }

            $window = array_slice($bpms, $left, $windowSize);
            sort($window);
            $mid = intdiv($windowSize, 2);
            $median = $windowSize % 2 === 1 ? $window[$mid] : ($window[$mid - 1] + $window[$mid]) / 2;

            if ($best === null || $median > $best) {
                $best = $median;
            }
        }

        return $best !== null ? (int) round($best) : null;
    }

    private static function windowStart(): string
    {
        return (new DateTimeImmutable('today'))->modify('-' . self::OBSERVED_WINDOW_DAYS . ' days')->format('Y-m-d H:i:s');
    }

    /**
     * This year's birthday, or last year's if this year's hasn't happened
     * yet - the date the current age-based estimate has been true since.
     * Known, disclosed edge case: a Feb 29 birth_date rolls to Mar 1 in a
     * non-leap current year (PHP's DateTimeImmutable::setDate behavior) -
     * affects one specific day, once every ~4 years, for leap-birthday users.
     */
    private static function currentBirthdayPeriodStart(string $birthDate): string
    {
        $today = new DateTimeImmutable('today');
        $birth = new DateTimeImmutable($birthDate);
        $thisYearBirthday = $birth->setDate((int) $today->format('Y'), (int) $birth->format('m'), (int) $birth->format('d'));
        $periodStart = $thisYearBirthday > $today ? $thisYearBirthday->modify('-1 year') : $thisYearBirthday;
        return $periodStart->format('Y-m-d');
    }

    /**
     * The classic 220-age estimate, or null if $birthDate produces an
     * implausible age (negative - a future birth_date - or over 130) rather
     * than silently computing/storing a nonsense number. bpm is SMALLINT
     * UNSIGNED, so a negative estimate would otherwise get clamped to 0 by
     * MySQL/MariaDB in non-strict mode instead of failing loudly.
     */
    private static function estimateFromAge(string $birthDate, string $atDate): ?int
    {
        $birth = new DateTimeImmutable($birthDate);
        $at = new DateTimeImmutable($atDate);
        $age = $birth->diff($at)->y;
        if ($birth > $at || $age > 130) {
            return null;
        }
        return 220 - $age;
    }
}

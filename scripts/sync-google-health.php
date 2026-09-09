<?php

declare(strict_types=1);

// Syncs the live Google Health API into the same schema/tables the Health
// Connect bulk importer (scripts/import-health-connect.php) populates.
//
// Usage:
//   php scripts/sync-google-health.php              (incremental: last 7 days)
//   php scripts/sync-google-health.php --days=N      (incremental: last N days)
//   php scripts/sync-google-health.php --full        (entire available history)
//   php scripts/sync-google-health.php --replay=RUN  (replay a prior run's
//                                                      recorded API responses
//                                                      instead of live calls)
//   php scripts/sync-google-health.php --no-log      (skip API request/response
//                                                      logging for this run)
//   php scripts/sync-google-health.php --debug       (also trace per-record
//                                                      processing decisions)
//
// Every live run records the raw request/response for every API call it
// makes to storage/api-logs/<run_id>/<endpoint>.jsonl (run_id is the same
// timestamp used for this run's storage/import-logs/*.log file, so the two
// are trivially correlated), plus a manifest.json capturing this run's
// --full/--days window. This is on by default (--no-log opts out — a --full
// resync over years of heart-rate data can log hundreds of MB) specifically
// so a run's exact inputs are available afterwards for debugging, without
// having to remember to ask for that up front. The Authorization header is
// never written to these logs — logging a bearer token to a plaintext file
// that persists indefinitely, even gitignored, is a real credential-exposure
// risk, not just noise.
//
// --replay=RUN re-runs the exact same parsing/ingestion code against a
// previously-recorded run's logs instead of the network: no OAuth token
// refresh happens, no live calls are made, and the original run's
// --full/--days window is restored automatically from its manifest.json
// (override with a fresh --days=N/--full if you deliberately want a
// different window applied to the same recorded data). This is what makes
// re-testing a parsing fix, or auditing exactly what a run received, cheap
// and reproducible instead of needing to hit the live API — and rolling API
// windows mean the same query re-run live later might not even return the
// same data any more.
//
// --debug adds one logLine() per processed record (via the new debugLog()
// helper) to the human-readable run log — matched food/brand and real-gram-
// vs-fallback match for nutrition, session/action for sleep/exercise/
// measurements/daily-resting-heart-rate. For the three high-volume
// insert-missing categories (steps, heart-rate, HRV) this traces per-*page*
// instead of per-row (tens of thousands of per-row lines wouldn't be
// practical to read) — a deliberate scope choice, same spirit as this file's
// other disclosed tradeoffs.
//
// Two genuinely different sync strategies, per category, confirmed against
// real API responses (storage/debug-metrics/*.json) rather than assumed:
//
//   - nutrition-log, sleep, exercise, weight, height: each dataPoint's
//     `name` field ends in a stable numeric ID -> real upsert via api_uid
//     (SELECT by (user_id, api_uid); INSERT if missing; UPDATE only if a
//     real column actually differs, so a routine re-sync of unchanged old
//     data doesn't spam the history trigger with no-op snapshots).
//   - daily-resting-heart-rate: no stable per-point ID, but the schema
//     already has a real natural key, UNIQUE(user_id, reading_date) -> same
//     upsert-if-changed approach, keyed on that instead of api_uid.
//   - steps, heart-rate, heart-rate-variability: NO stable ID of any kind
//     (confirmed: no `name` field on these dataPoints at all), and this
//     schema's BEFORE DELETE trigger makes a delete-and-reinsert reconcile
//     impossible. Disclosed scope reduction: dedup here is INSERT-MISSING,
//     not a true reconcile — one indexed SELECT of existing reading_time
//     values across the window, then skip any incoming point already
//     present (regardless of which source put it there — this is what
//     stops the routine sync from re-duplicating whatever the Health
//     Connect bulk import already covered). This is fine in practice
//     because passively-sampled continuous sensor data is not realistically
//     ever edited after the fact, unlike food/sleep/exercise/weight.
//
// KNOWN, DISCLOSED GAP (not solved here): Health Connect's api_uid (its own
// local `uuid`) and this script's api_uid (the live API's cloud dataPoint
// id) are different ID spaces for the exact same real-world event, so the
// UNIQUE(user_id, api_uid) constraint cannot detect that a sleep session /
// exercise session / weight reading / food log entry already exists from
// the OTHER source. Same class of problem as the already-documented,
// already-deferred "upsert priority across sources" open item. Practical
// guidance until real cross-source reconciliation is designed: pick a
// --days/--full window for the first run that starts after whatever the
// last Health Connect export already covered, to avoid overlap.
//
// Nutrition additionally fetches the referenced `food` resource per entry
// (cached per run) to compute REAL gram-per-serving-unit conversions,
// rather than the placeholder "100" unit the Health Connect importer has to
// use (HC reports no serving/quantity at all; the live API does). Falls
// back to the same ratio-based placeholder-unit approach as
// import-health-connect.php's findOrCreateFood() when the food resource
// has no gram entry or the log's unit can't be matched.
//
// mixed-conflict resolution stays unbuilt, as already documented elsewhere
// — this sync only overwrites-if-different for its own re-runs, it doesn't
// detect or record a genuine value disagreement between two sources.

require __DIR__ . '/../src/Env.php';
require __DIR__ . '/../src/GoogleOAuth.php';
require __DIR__ . '/../src/TokenStore.php';
require __DIR__ . '/../src/Database.php';

Env::load(__DIR__ . '/../.env');

$isFull = in_array('--full', $argv, true);
$fullArgGiven = $isFull;
$days = 7;
$daysArgGiven = false;
$noLog = in_array('--no-log', $argv, true);
$debug = in_array('--debug', $argv, true);
$replayRunId = null;
foreach ($argv as $arg) {
    if (preg_match('/^--days=(\d+)$/', $arg, $m)) {
        $days = (int) $m[1];
        $daysArgGiven = true;
    }
    if (preg_match('/^--replay=(.+)$/', $arg, $m)) {
        $replayRunId = $m[1];
    }
}

$runId = date('Ymd-His');

$logDir = __DIR__ . '/../storage/import-logs';
if (!is_dir($logDir)) {
    mkdir($logDir, 0777, true);
}
$logPath = $logDir . '/sync-google-health-' . $runId . ($replayRunId !== null ? "-replay-of-{$replayRunId}" : '') . '.log';
$logFile = fopen($logPath, 'w');

$runStats = [];
$startedAt = microtime(true);

function logLine(string $message): void
{
    global $logFile;
    $line = '[' . date('Y-m-d H:i:s') . '] ' . $message;
    echo $line . "\n";
    fwrite($logFile, $line . "\n");
}

function bumpStat(string $category, string $key, int $by = 1): void
{
    global $runStats;
    $runStats[$category][$key] = ($runStats[$category][$key] ?? 0) + $by;
}

/** One logLine() per processed record/page when --debug is set; a silent no-op otherwise. */
function debugLog(string $message): void
{
    global $debug;
    if ($debug) {
        logLine("DEBUG {$message}");
    }
}

/**
 * Append-only JSONL writer for one run's raw API request/response pairs —
 * one file per $logKey (endpoint name), opened lazily. Never receives the
 * Authorization header; see the file header comment for why.
 */
final class ApiLogger
{
    private array $handles = [];

    public function __construct(private string $runDir)
    {
        if (!is_dir($this->runDir)) {
            mkdir($this->runDir, 0777, true);
        }
    }

    public function record(string $logKey, array $request, array $response): void
    {
        if (!isset($this->handles[$logKey])) {
            $this->handles[$logKey] = fopen("{$this->runDir}/{$logKey}.jsonl", 'a');
        }
        $line = json_encode(['timestamp' => date('c'), 'request' => $request, 'response' => $response]);
        fwrite($this->handles[$logKey], $line . "\n");
    }

    public function writeManifest(array $manifest): void
    {
        file_put_contents("{$this->runDir}/manifest.json", json_encode($manifest, JSON_PRETTY_PRINT));
    }
}

/**
 * Reads a prior run's ApiLogger output back, in the same order it was
 * recorded, so --replay can feed the exact same parsing code without any
 * network access. Once a $logKey's recorded responses are exhausted, hands
 * back a synthetic empty page — streamDataPoints()'s own "no more points"
 * check already treats that as the end of pagination, so no special-casing
 * is needed on the reading side.
 */
final class ReplayReader
{
    private array $lines = [];
    private array $cursor = [];

    public function __construct(private string $runDir)
    {
    }

    public function readManifest(): ?array
    {
        $path = "{$this->runDir}/manifest.json";
        return is_file($path) ? json_decode(file_get_contents($path), true) : null;
    }

    private function ensureLoaded(string $logKey): void
    {
        if (isset($this->lines[$logKey])) {
            return;
        }
        $path = "{$this->runDir}/{$logKey}.jsonl";
        $entries = [];
        if (is_file($path)) {
            foreach (file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
                $entries[] = json_decode($line, true);
            }
        }
        $this->lines[$logKey] = $entries;
        $this->cursor[$logKey] = 0;
    }

    public function next(string $logKey): array
    {
        $this->ensureLoaded($logKey);
        $i = $this->cursor[$logKey];
        if (!isset($this->lines[$logKey][$i])) {
            return ['status' => 200, 'body' => json_encode(['dataPoints' => []])];
        }
        $this->cursor[$logKey]++;
        return $this->lines[$logKey][$i]['response'];
    }
}

/** The only place curl gets invoked — replay mode short-circuits it entirely. */
function apiCall(string $url, string $logKey, string $accessToken): array
{
    global $apiLogger, $replayReader;

    if ($replayReader !== null) {
        return $replayReader->next($logKey);
    }

    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_HTTPHEADER => ['Authorization: Bearer ' . $accessToken, 'Accept: application/json'],
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 30,
    ]);
    $body = curl_exec($ch);
    $status = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    $result = ['status' => $status, 'body' => $body === false ? '' : $body];

    if ($apiLogger !== null) {
        $apiLogger->record($logKey, ['method' => 'GET', 'url' => $url], $result);
    }

    return $result;
}

logLine("=== NutriPal Google Health API sync starting ===");

$apiLogDir = __DIR__ . '/../storage/api-logs';
$apiLogger = null;
$replayReader = null;

if ($replayRunId !== null) {
    $replayReader = new ReplayReader("{$apiLogDir}/{$replayRunId}");
    $manifest = $replayReader->readManifest();
    if ($manifest === null) {
        logLine("ERROR: no manifest.json found for replay run '{$replayRunId}' under storage/api-logs/ — was it logged?");
        exit(1);
    }
    if (!$daysArgGiven && isset($manifest['days'])) {
        $days = (int) $manifest['days'];
    }
    if (!$fullArgGiven && isset($manifest['isFull'])) {
        $isFull = (bool) $manifest['isFull'];
    }
    logLine("Mode: REPLAY of run '{$replayRunId}' — no live API calls will be made");
} elseif (!$noLog) {
    $apiLogger = new ApiLogger("{$apiLogDir}/{$runId}");
}

logLine($isFull ? "Mode: FULL resync (entire available history)" : "Mode: incremental, last {$days} day(s)");
logLine("Log: {$logPath}");
if ($debug) {
    logLine("Debug logging: ON");
}

if ($replayRunId !== null) {
    logLine("Skipping OAuth token refresh — replay mode makes no network calls");
    $accessToken = '';
} else {
    $tokenStore = new TokenStore(__DIR__ . '/../storage/google-tokens.json');
    $tokens = $tokenStore->load();
    if ($tokens === null || !isset($tokens['refresh_token'])) {
        logLine("ERROR: no stored tokens with a refresh_token. Run the OAuth flow (auth-login.php) first.");
        exit(1);
    }

    $oauth = new GoogleOAuth(
        clientId: Env::require('GOOGLE_CLIENT_ID'),
        clientSecret: Env::require('GOOGLE_CLIENT_SECRET'),
        redirectUri: Env::require('GOOGLE_REDIRECT_URI')
    );
    $refreshed = $oauth->refreshAccessToken($tokens['refresh_token']);
    $tokenStore->save($refreshed);
    $accessToken = $refreshed['access_token'];
}

$pdo = Database::connect();
logLine("Connected to MySQL database " . Env::get('DB_NAME'));

$userId = 2;
$cutoff = $isFull ? null : (new DateTimeImmutable('today', new DateTimeZone('UTC')))->modify("-{$days} days");

if ($apiLogger !== null) {
    $apiLogger->writeManifest(['isFull' => $isFull, 'days' => $days, 'startedAt' => date('c')]);
}

// ----------------------------------------------------------------------------
// Lookup caches
// ----------------------------------------------------------------------------

function loadLookup(PDO $pdo, string $table, string $column = 'name'): array
{
    $map = [];
    foreach ($pdo->query("SELECT id, {$column} FROM {$table}") as $row) {
        $map[$row[$column]] = (int) $row['id'];
    }
    return $map;
}

$mealTypeIds = loadLookup($pdo, 'lut_meal_type');
$nutrientIds = loadLookup($pdo, 'lut_nutrient');
$unitIds = loadLookup($pdo, 'unit_conversions');
$sleepStageTypeIds = loadLookup($pdo, 'lut_sleep_stage_type');
$sleepTypeIds = loadLookup($pdo, 'lut_sleep_type');
$recordingMethodIds = loadLookup($pdo, 'lut_recording_method');
$measurementTypeIds = loadLookup($pdo, 'lut_measurement_type');
$dataSourceIds = loadLookup($pdo, 'lut_data_source');
$activityTypeIds = loadLookup($pdo, 'lut_activity_type');
$calcMethodIds = loadLookup($pdo, 'lut_heart_rate_calc_method');
$ingestionSourceApi = (int) $pdo->query("SELECT id FROM lut_ingestion_source WHERE name='google_health_api'")->fetchColumn();
$ingestionSourceMixed = (int) $pdo->query("SELECT id FROM lut_ingestion_source WHERE name='mixed'")->fetchColumn();
$gramUnitId = $unitIds['gram'];
$mmUnitId = $unitIds['millimeter'];
$meterUnitId = $unitIds['meter'];
$massDimensionId = (int) $pdo->query("SELECT id FROM lut_dimension WHERE name='mass'")->fetchColumn();

logLine("Lookup caches loaded: " . count($mealTypeIds) . " meal types, " . count($nutrientIds) . " nutrients, "
    . count($dataSourceIds) . " known data sources");

$insertDataSource = $pdo->prepare("INSERT INTO lut_data_source (name) VALUES (?)");
function findOrCreateDataSource(?string $name, PDO $pdo, array &$cache, PDOStatement $insertStmt): ?int
{
    if ($name === null || $name === '') {
        return null;
    }
    if (isset($cache[$name])) {
        return $cache[$name];
    }
    try {
        $insertStmt->execute([$name]);
        $id = (int) $pdo->lastInsertId();
    } catch (PDOException $e) {
        if ((int) ($e->errorInfo[1] ?? 0) !== 1062) {
            throw $e;
        }
        // lut_data_source.name uses a case-insensitive collation (matches
        // MySQL default) — a source can report the same real device/app
        // under different casing (e.g. Health Connect's app name "Fitbit"
        // vs. the live API's dataSource.platform "FITBIT"). Look up the
        // row the collation already considers this a duplicate of.
        $find = $pdo->prepare("SELECT id FROM lut_data_source WHERE name = ?");
        $find->execute([$name]);
        $id = (int) $find->fetchColumn();
    }
    $cache[$name] = $id;
    return $id;
}

$insertActivityType = $pdo->prepare("INSERT INTO lut_activity_type (name) VALUES (?)");
function findOrCreateActivityType(?string $name, PDO $pdo, array &$cache, PDOStatement $insertStmt): ?int
{
    if ($name === null || $name === '') {
        return null;
    }
    if (isset($cache[$name])) {
        return $cache[$name];
    }
    try {
        $insertStmt->execute([$name]);
        $id = (int) $pdo->lastInsertId();
    } catch (PDOException $e) {
        if ((int) ($e->errorInfo[1] ?? 0) !== 1062) {
            throw $e;
        }
        $find = $pdo->prepare("SELECT id FROM lut_activity_type WHERE name = ?");
        $find->execute([$name]);
        $id = (int) $find->fetchColumn();
    }
    $cache[$name] = $id;
    return $id;
}

// ----------------------------------------------------------------------------
// Shared helpers
// ----------------------------------------------------------------------------

function toMysqlDateTime(string $iso): string
{
    return (new DateTimeImmutable($iso))->format('Y-m-d H:i:s');
}

function civilDate(array $date): string
{
    return sprintf('%04d-%02d-%02d', $date['year'], $date['month'], $date['day']);
}

function apiUidFrom(array $point): ?string
{
    if (!isset($point['name'])) {
        return null;
    }
    $slash = strrpos($point['name'], '/');
    return $slash === false ? $point['name'] : substr($point['name'], $slash + 1);
}

function dataSourceLabel(array $point): ?string
{
    return $point['dataSource']['device']['displayName'] ?? $point['dataSource']['platform'] ?? null;
}

/** Extracts the best-available date out of a data point, for client-side cutoff filtering during pagination. */
function pointCivilDate(string $bodyKey, array $point): ?DateTimeImmutable
{
    $body = $point[$bodyKey] ?? null;
    if ($body === null) {
        return null;
    }
    if (isset($body['interval']['civilStartTime']['date'])) {
        return new DateTimeImmutable(civilDate($body['interval']['civilStartTime']['date']));
    }
    if (isset($body['sampleTime']['civilTime']['date'])) {
        return new DateTimeImmutable(civilDate($body['sampleTime']['civilTime']['date']));
    }
    if (isset($body['date'])) {
        return new DateTimeImmutable(civilDate($body['date']));
    }
    if (isset($body['interval']['startTime'])) {
        return new DateTimeImmutable(substr($body['interval']['startTime'], 0, 10), new DateTimeZone('UTC'));
    }
    if (isset($body['sampleTime']['physicalTime'])) {
        return new DateTimeImmutable(substr($body['sampleTime']['physicalTime'], 0, 10), new DateTimeZone('UTC'));
    }
    return null;
}

/**
 * Streams every dataPoint for one Google Health data type, newest-first,
 * calling $onPoint per point. Stops at $cutoff (client-side, since only
 * some data types accept server-side interval filtering) or, in full mode
 * ($cutoff === null), once the API stops returning pages. $onPageComplete,
 * if given, fires once per page (after every point in it has been passed to
 * $onPoint) with (page number, point count) — used for per-page --debug
 * tracing on the high-volume categories where per-point tracing isn't
 * practical.
 */
function streamDataPoints(string $accessToken, string $dataType, string $bodyKey, ?DateTimeImmutable $cutoff, callable $onPoint, ?callable $onPageComplete = null): void
{
    $pageToken = null;
    $maxPages = 20000;

    for ($page = 0; $page < $maxPages; $page++) {
        $params = ['pageSize' => 500];
        if ($pageToken !== null) {
            $params['pageToken'] = $pageToken;
        }
        $url = 'https://health.googleapis.com/v4/users/me/dataTypes/' . $dataType . '/dataPoints?' . http_build_query($params);

        $result = apiCall($url, $dataType, $accessToken);
        $status = $result['status'];
        $body = $result['body'];

        if ($status !== 200) {
            logLine("ERROR fetching {$dataType} page {$page}: HTTP {$status}");
            return;
        }
        $decoded = json_decode($body, true) ?? [];
        $points = $decoded['dataPoints'] ?? [];
        if (empty($points)) {
            return;
        }

        $reachedCutoff = false;
        foreach ($points as $point) {
            if ($cutoff !== null) {
                $date = pointCivilDate($bodyKey, $point);
                if ($date !== null && $date < $cutoff) {
                    $reachedCutoff = true;
                    continue;
                }
            }
            $onPoint($point);
        }

        if ($onPageComplete !== null) {
            $onPageComplete($page, count($points));
        }

        $pageToken = $decoded['nextPageToken'] ?? null;
        if ($reachedCutoff || $pageToken === null || $pageToken === '') {
            return;
        }
    }
    logLine("WARN {$dataType}: hit the {$maxPages}-page safety cap without exhausting pagination");
}

function looksLikeMysqlDateTime($val): bool
{
    return is_string($val) && preg_match('/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/', $val) === 1;
}

/**
 * Generic upsert for the categories with a real native ID (or, for
 * daily_resting_heart_rate, a real natural key). $data is compared against
 * the existing row (if any) with a small numeric tolerance; an UPDATE is
 * only issued if something actually differs, so routine re-syncs of
 * unchanged data don't spam the history trigger with no-op snapshots.
 * $provenance (changed_by/changed_by_user_id/db_ts) is stamped only when a
 * real update happens.
 *
 * $crossSourceCols/$crossSourceVals (optional): a second identity check for
 * tables where Health Connect and the live API assign different api_uids to
 * the same real-world event (sleep/exercise sessions, measurements) - if the
 * primary (user_id, api_uid) lookup misses but this alternate lookup (e.g.
 * user_id + start_time) hits, the row already exists under the other
 * source's api_uid. This does NOT just skip: Health Connect and the live API
 * each have fields the other lacks entirely (e.g. Health Connect's exercise
 * sessions never carry calories/distance/steps/avg-heart-rate at all), so a
 * blind skip would silently drop real, complementary data the other source
 * has. Instead: any $data field that's genuinely new (existing value NULL,
 * incoming non-NULL) gets filled in via UPDATE; a field where both sources
 * disagree on a non-NULL value is a real conflict, recorded by filling it in
 * anyway AND flipping ingestion_source_id to the 'mixed' sentinel
 * ($mixedIngestionSourceId) - reserved for exactly this since the schema was
 * first drafted, now actually exercised. A cross-source match with nothing
 * new to add is skipped, same as before.
 */
function upsertByNaturalKey(PDO $pdo, string $table, array $whereCols, array $whereVals, array $data, array $provenance,
    ?array $crossSourceCols = null, ?array $crossSourceVals = null, ?int $mixedIngestionSourceId = null): string
{
    $whereSql = implode(' AND ', array_map(fn($c) => "{$c} = ?", $whereCols));
    $stmt = $pdo->prepare("SELECT * FROM {$table} WHERE {$whereSql}");
    $stmt->execute($whereVals);
    $existing = $stmt->fetch(PDO::FETCH_ASSOC);

    if ($existing === false && $crossSourceCols !== null) {
        $altSql = implode(' AND ', array_map(fn($c) => "{$c} = ?", $crossSourceCols));
        $altStmt = $pdo->prepare("SELECT * FROM {$table} WHERE {$altSql}");
        $altStmt->execute($crossSourceVals);
        $altExisting = $altStmt->fetch(PDO::FETCH_ASSOC);
        if ($altExisting !== false) {
            // Provenance columns are expected to differ by source (that's
            // the whole point of the columns) - never a real conflict, and
            // never worth overwriting the row's existing provenance for.
            // activity_type_id/activity_name are excluded for a more
            // specific reason: activity_type_id is a plain find-or-create
            // keyed on each source's own raw activity code, prefixed
            // 'HC_'/'API_' - so it's *guaranteed* to differ for the same
            // real activity across sources (confirmed: 1979/1979 real
            // cross-source exercise matches hit this). activity_name is the
            // same problem one level up - each source has its own labeling
            // convention for the same activity (confirmed real case: HC's
            // generic title vs. the live API's "Treadmill run"). Both are a
            // structural gap already tracked separately (no canonical
            // cross-source activity mapping yet), not a per-instance
            // disagreement worth flagging as 'mixed' every single time.
            $neverConflict = ['data_source_id', 'recording_method_id', 'ingestion_source_id', 'activity_type_id', 'activity_name'];
            $fillable = [];
            $conflicting = [];
            foreach ($data as $col => $val) {
                $old = $altExisting[$col] ?? null;
                if ($val === null || (string) $val === (string) $old) {
                    continue;
                }
                if (in_array($col, $neverConflict, true)) {
                    continue;
                }
                if ($old === null || $old === '') {
                    $fillable[$col] = $val;
                } elseif (is_numeric($val) && is_numeric($old)
                    && abs((float) $old - (float) $val) <= max(0.0005, 0.01 * max(abs((float) $old), abs((float) $val)))) {
                    // 1% relative tolerance (floor 0.0005 for near-zero
                    // values) - covers e.g. weight rounded to the nearest
                    // 100g by Health Connect vs. the live API's single-gram
                    // precision (confirmed real delta: up to ~100g out of
                    // ~100,000g, comfortably under 1%) without masking a
                    // genuinely different calorie/distance/duration value.
                    continue;
                } elseif (looksLikeMysqlDateTime($val) && looksLikeMysqlDateTime($old)
                    && abs(strtotime($val) - strtotime($old)) <= 300) {
                    // A session's end_time (unlike its start_time, the
                    // identity key) can drift by up to ~1 minute between
                    // sources - stage-boundary rounding, not a real
                    // disagreement. 5-minute tolerance to be safe.
                    continue;
                } else {
                    $conflicting[$col] = $val;
                }
            }
            if (empty($fillable) && empty($conflicting)) {
                return 'skipped_cross_source';
            }
            $setFields = $fillable + $conflicting;
            if (!empty($conflicting) && $mixedIngestionSourceId !== null) {
                $setFields['ingestion_source_id'] = $mixedIngestionSourceId;
            }
            $setFields = array_merge($setFields, $provenance);
            $setSql = implode(', ', array_map(fn($c) => "{$c} = ?", array_keys($setFields)));
            $pdo->prepare("UPDATE {$table} SET {$setSql} WHERE {$altSql}")
                ->execute(array_merge(array_values($setFields), $crossSourceVals));
            return empty($conflicting) ? 'merged_cross_source' : 'merged_conflict';
        }
    }

    if ($existing === false) {
        $cols = array_merge($whereCols, array_keys($data));
        $vals = array_merge($whereVals, array_values($data));
        $placeholders = implode(',', array_fill(0, count($cols), '?'));
        $pdo->prepare("INSERT INTO {$table} (" . implode(',', $cols) . ") VALUES ({$placeholders})")->execute($vals);
        return 'inserted';
    }

    $changed = [];
    foreach ($data as $col => $val) {
        $old = $existing[$col] ?? null;
        if ($val === null && $old === null) {
            continue;
        }
        if (is_numeric($val) && is_numeric($old)) {
            if (abs((float) $old - (float) $val) > 0.0005) {
                $changed[$col] = $val;
            }
        } elseif ((string) $old !== (string) $val) {
            $changed[$col] = $val;
        }
    }
    if (empty($changed)) {
        return 'skipped';
    }
    $changed = array_merge($changed, $provenance);
    $setSql = implode(', ', array_map(fn($c) => "{$c} = ?", array_keys($changed)));
    $pdo->prepare("UPDATE {$table} SET {$setSql} WHERE {$whereSql}")->execute(array_merge(array_values($changed), $whereVals));
    return 'updated';
}

function provenanceNow(int $userId): array
{
    return [
        'db_ts' => date('Y-m-d H:i:s'),
        'changed_by' => 'sync-google-health.php',
        'changed_by_user_id' => $userId,
    ];
}

// ----------------------------------------------------------------------------
// 1. Nutrition -> food_log_entries / foods_db
// ----------------------------------------------------------------------------

const HC_STYLE_NUTRIENT_KEYS = [
    'SODIUM', 'POTASSIUM', 'DIETARY_FIBER', 'SUGAR', 'CALCIUM', 'IRON', 'VITAMIN_A', 'VITAMIN_C',
    'CHOLESTEROL', 'SATURATED_FAT', 'TRANS_FAT', 'BIOTIN', 'COPPER', 'FOLIC_ACID', 'IODINE',
    'MAGNESIUM', 'NIACIN', 'PANTOTHENIC_ACID', 'PHOSPHORUS', 'RIBOFLAVIN', 'THIAMIN', 'VITAMIN_B12',
    'VITAMIN_B6', 'VITAMIN_D', 'VITAMIN_E', 'ZINC', 'MANGANESE', 'SELENIUM', 'CHLORIDE', 'MOLYBDENUM',
    'CHROMIUM', 'VITAMIN_K', 'CAFFEINE', 'FOLATE',
];

/** Fetches the referenced `food` resource once (cached per run) and returns its servings, keyed by lowercased unit display name (singular and plural both map to the same entry). */
function fetchFoodServings(string $accessToken, string $foodRef, array &$cache): ?array
{
    if (array_key_exists($foodRef, $cache)) {
        return $cache[$foodRef];
    }
    $url = 'https://health.googleapis.com/v4/' . $foodRef;
    $result = apiCall($url, 'food', $accessToken);
    $status = $result['status'];
    $body = $result['body'];

    if ($status !== 200) {
        $cache[$foodRef] = null;
        return null;
    }
    $decoded = json_decode($body, true);
    $servings = $decoded['food']['servings'] ?? [];

    $gramMultiplier = null;
    $byUnit = [];
    foreach ($servings as $s) {
        $mult = $s['multiplier'] ?? null;
        if ($mult === null) {
            continue;
        }
        foreach (['foodMeasurementUnitDisplayName', 'foodMeasurementUnitDisplayNamePlural'] as $nameField) {
            if (isset($s[$nameField])) {
                $byUnit[strtolower($s[$nameField])] = (float) $mult;
            }
        }
        if (isset($s['foodMeasurementUnitDisplayName']) && strtolower($s['foodMeasurementUnitDisplayName']) === 'gram') {
            $gramMultiplier = (float) $mult;
        }
    }

    // brand is only present on some foods (packaged/branded items) — confirmed
    // via real data that it's a real field, just conditionally populated, not
    // absent from the API entirely. Kept separate from gramMultiplier/byUnit
    // below (nullable) so a food with no gram entry still yields its brand.
    $result = [
        'brand' => $decoded['food']['brand'] ?? null,
        'gramMultiplier' => ($gramMultiplier !== null && $gramMultiplier > 0) ? $gramMultiplier : null,
        'byUnit' => $byUnit,
    ];
    $cache[$foodRef] = $result;
    return $result;
}

/** Real grams for one unit of $unitLabel, using the food's own "gram" entry as a pivot. Null if the unit isn't listed. */
function resolveGramsPerUnit(array $foodServings, string $unitLabel): ?float
{
    if ($foodServings['gramMultiplier'] === null) {
        return null;
    }
    $mult = $foodServings['byUnit'][strtolower($unitLabel)] ?? null;
    if ($mult === null) {
        return null;
    }
    return $mult / $foodServings['gramMultiplier'];
}

/** Same ratio-based fallback import-health-connect.php's findOrCreateFood() uses, for when real grams can't be resolved. */
function findOrCreateFoodFallback(PDO $pdo, int $userId, int $massDimensionId, string $name, ?string $brandName,
    ?float $energyKcal, ?float $proteinG, ?float $carbG, ?float $fatG,
    array $micronutrients, array &$nutrientIds, int $gramUnitId, array &$servingUnitCache): array
{
    $existing = $pdo->prepare(
        "SELECT id, version, energy_kcal, total_protein_g, total_carbohydrate_g, total_fat_g
         FROM foods_db WHERE name = ? AND brand_name <=> ? AND dimension_id = ? AND user_id = ?
         ORDER BY COALESCE(version, 0) DESC"
    );
    $existing->execute([$name, $brandName, $massDimensionId, $userId]);
    $candidates = $existing->fetchAll(PDO::FETCH_ASSOC);

    $impliedRatio = function (?float $incoming, ?float $baseline): ?float {
        if ($incoming === null || $baseline === null || abs($baseline) < 0.001) {
            return null;
        }
        return $incoming / $baseline;
    };

    foreach ($candidates as $row) {
        $ratios = array_filter([
            $impliedRatio($energyKcal, $row['energy_kcal'] !== null ? (float) $row['energy_kcal'] : null),
            $impliedRatio($proteinG, $row['total_protein_g'] !== null ? (float) $row['total_protein_g'] : null),
            $impliedRatio($carbG, $row['total_carbohydrate_g'] !== null ? (float) $row['total_carbohydrate_g'] : null),
            $impliedRatio($fatG, $row['total_fat_g'] !== null ? (float) $row['total_fat_g'] : null),
        ], fn($r) => $r !== null && $r > 0);

        if (count($ratios) === 0) {
            continue;
        }
        sort($ratios);
        $median = $ratios[intdiv(count($ratios), 2)];
        $consistent = true;
        foreach ($ratios as $r) {
            if (abs($r - $median) > $median * 0.15) {
                $consistent = false;
                break;
            }
        }
        if ($consistent) {
            $foodId = (int) $row['id'];
            $servingUnitId = $servingUnitCache[$foodId] ?? null;
            if ($servingUnitId === null) {
                // Matched a food created by a previous run (or by the
                // Health Connect importer) whose custom unit isn't in this
                // run's in-memory cache — look it up rather than fail.
                $lookup = $pdo->prepare(
                    "SELECT lsu.id FROM lut_serving_unit lsu
                     JOIN foods_db_custom_units fdcu ON fdcu.id = lsu.foods_db_custom_unit_id
                     WHERE fdcu.food_id = ? ORDER BY fdcu.is_default DESC LIMIT 1"
                );
                $lookup->execute([$foodId]);
                $servingUnitId = (int) $lookup->fetchColumn();
                $servingUnitCache[$foodId] = $servingUnitId;
            }
            return [$foodId, false, round($median, 4), $servingUnitId];
        }
    }

    $latestVersion = empty($candidates) ? null : ((int) $candidates[0]['version']);
    $newVersion = $latestVersion === null ? null : ($latestVersion + 1);
    $insert = $pdo->prepare(
        "INSERT INTO foods_db (name, brand_name, dimension_id, version, group_id, user_id, energy_kcal, total_protein_g, total_carbohydrate_g, total_fat_g)
         VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?)"
    );
    $insert->execute([$name, $brandName, $massDimensionId, $newVersion, $userId, $energyKcal, $proteinG, $carbG, $fatG]);
    $foodId = (int) $pdo->lastInsertId();
    insertFoodNutrients($pdo, $foodId, $micronutrients, $nutrientIds, $gramUnitId);

    $servingUnitId = getOrCreateCustomUnit($pdo, $foodId, 'reported serving', 100.0, "api_reported_serving_{$foodId}", true);
    $servingUnitCache[$foodId] = $servingUnitId;
    return [$foodId, true, 1.0, $servingUnitId];
}

function insertFoodNutrients(PDO $pdo, int $foodId, array $micronutrients, array &$nutrientIds, int $gramUnitId): void
{
    if (empty($micronutrients)) {
        return;
    }
    $insertNutrient = $pdo->prepare("INSERT INTO foods_db_nutrients (food_id, nutrient_id, quantity, unit_id) VALUES (?, ?, ?, ?)");
    foreach ($micronutrients as $nutrientName => $qty) {
        if (!isset($nutrientIds[$nutrientName])) {
            continue;
        }
        $insertNutrient->execute([$foodId, $nutrientIds[$nutrientName], $qty, $gramUnitId]);
    }
}

function getOrCreateCustomUnit(PDO $pdo, int $foodId, string $unitName, float $equivalentAmount, string $servingUnitLabel, bool $isDefault): int
{
    $find = $pdo->prepare("SELECT id FROM foods_db_custom_units WHERE food_id = ? AND unit_name = ?");
    $find->execute([$foodId, $unitName]);
    $customUnitId = $find->fetchColumn();

    if ($customUnitId === false) {
        $insert = $pdo->prepare("INSERT INTO foods_db_custom_units (food_id, unit_name, equivalent_amount, is_default) VALUES (?, ?, ?, ?)");
        $insert->execute([$foodId, $unitName, $equivalentAmount, $isDefault ? 1 : 0]);
        $customUnitId = (int) $pdo->lastInsertId();
    } else {
        $customUnitId = (int) $customUnitId;
    }

    $findServingUnit = $pdo->prepare("SELECT id FROM lut_serving_unit WHERE foods_db_custom_unit_id = ?");
    $findServingUnit->execute([$customUnitId]);
    $servingUnitId = $findServingUnit->fetchColumn();
    if ($servingUnitId !== false) {
        return (int) $servingUnitId;
    }

    $insertServingUnit = $pdo->prepare("INSERT INTO lut_serving_unit (label, foods_db_custom_unit_id) VALUES (?, ?)");
    $insertServingUnit->execute([$servingUnitLabel, $customUnitId]);
    return (int) $pdo->lastInsertId();
}

/**
 * Real-gram nutrition matching: since the live API gives a genuine serving
 * quantity (unlike Health Connect), normalizing to per-100g from a SINGLE
 * entry is exact, not ratio-inferred. Falls back to
 * findOrCreateFoodFallback() when the food resource has no usable gram
 * conversion. Returns [foodId, wasNewVersion, servingAmount, servingUnitId].
 */
function findOrCreateFoodReal(PDO $pdo, int $userId, int $massDimensionId, string $name, ?string $brandName,
    float $gramsForEntry, float $servingAmount, string $unitLabel, float $gramsPerUnit,
    ?float $energyKcal, ?float $proteinG, ?float $carbG, ?float $fatG,
    array $micronutrients, array &$nutrientIds, int $gramUnitId): array
{
    $scale = fn(?float $v): ?float => $v === null ? null : ($v / $gramsForEntry * 100);
    $energyPer100 = $scale($energyKcal);
    $proteinPer100 = $scale($proteinG);
    $carbPer100 = $scale($carbG);
    $fatPer100 = $scale($fatG);
    $microPer100 = [];
    foreach ($micronutrients as $n => $v) {
        $microPer100[$n] = $v / $gramsForEntry * 100;
    }

    $existing = $pdo->prepare(
        "SELECT id, version, energy_kcal, total_protein_g, total_carbohydrate_g, total_fat_g
         FROM foods_db WHERE name = ? AND brand_name <=> ? AND dimension_id = ? AND user_id = ?
         ORDER BY COALESCE(version, 0) DESC"
    );
    $existing->execute([$name, $brandName, $massDimensionId, $userId]);
    $candidates = $existing->fetchAll(PDO::FETCH_ASSOC);

    $closeEnough = function (?float $a, ?float $b): bool {
        if ($a === null && $b === null) {
            return true;
        }
        if ($a === null || $b === null) {
            return false;
        }
        $base = max(abs($a), abs($b), 0.5);
        return abs($a - $b) / $base <= 0.05;
    };

    $foodId = null;
    $isNew = false;
    foreach ($candidates as $row) {
        if ($closeEnough($energyPer100, $row['energy_kcal'] !== null ? (float) $row['energy_kcal'] : null)
            && $closeEnough($proteinPer100, $row['total_protein_g'] !== null ? (float) $row['total_protein_g'] : null)
            && $closeEnough($carbPer100, $row['total_carbohydrate_g'] !== null ? (float) $row['total_carbohydrate_g'] : null)
            && $closeEnough($fatPer100, $row['total_fat_g'] !== null ? (float) $row['total_fat_g'] : null)) {
            $foodId = (int) $row['id'];
            break;
        }
    }

    if ($foodId === null) {
        $isNew = true;
        $latestVersion = empty($candidates) ? null : ((int) $candidates[0]['version']);
        $newVersion = $latestVersion === null ? null : ($latestVersion + 1);
        $insert = $pdo->prepare(
            "INSERT INTO foods_db (name, brand_name, dimension_id, version, group_id, user_id, energy_kcal, total_protein_g, total_carbohydrate_g, total_fat_g)
             VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?)"
        );
        $insert->execute([$name, $brandName, $massDimensionId, $newVersion, $userId, $energyPer100, $proteinPer100, $carbPer100, $fatPer100]);
        $foodId = (int) $pdo->lastInsertId();
        insertFoodNutrients($pdo, $foodId, $microPer100, $nutrientIds, $gramUnitId);
    }

    $unitNameKey = strtolower(trim($unitLabel)) ?: 'unit';
    $servingUnitId = getOrCreateCustomUnit($pdo, $foodId, $unitNameKey, $gramsPerUnit, "api_{$foodId}_{$unitNameKey}", $isNew);

    return [$foodId, $isNew, $servingAmount, $servingUnitId];
}

function syncNutrition(string $accessToken, PDO $pdo, int $userId, int $ingestionSource, int $massDimensionId, int $gramUnitId,
    array $mealTypeIds, array &$nutrientIds, array &$dataSourceIds, PDOStatement $insertDataSourceStmt, ?DateTimeImmutable $cutoff): void
{
    logLine("--- Nutrition (nutrition-log) ---");
    $foodResourceCache = [];
    $fallbackServingUnitCache = [];

    streamDataPoints($accessToken, 'nutrition-log', 'nutritionLog', $cutoff, function (array $point) use (
        $accessToken, $pdo, $userId, $ingestionSource, $massDimensionId, $gramUnitId, $mealTypeIds,
        &$nutrientIds, &$dataSourceIds, $insertDataSourceStmt, &$foodResourceCache, &$fallbackServingUnitCache
    ) {
        bumpStat('nutrition', 'rows_seen', 1);
        $nl = $point['nutritionLog'];
        $name = trim((string) ($nl['foodDisplayName'] ?? ''));
        if ($name === '') {
            bumpStat('nutrition', 'skipped_error', 1);
            return;
        }
        $mealTypeId = $mealTypeIds[$nl['mealType'] ?? ''] ?? null;
        if ($mealTypeId === null) {
            logLine("WARN nutrition api_uid=" . (apiUidFrom($point) ?? '?') . ": unmapped mealType '" . ($nl['mealType'] ?? '') . "'");
            bumpStat('nutrition', 'skipped_error', 1);
            return;
        }

        $energyKcal = isset($nl['energy']['kcal']) ? (float) $nl['energy']['kcal'] : null;
        $carbG = isset($nl['totalCarbohydrate']['grams']) ? (float) $nl['totalCarbohydrate']['grams'] : null;
        $fatG = isset($nl['totalFat']['grams']) ? (float) $nl['totalFat']['grams'] : null;
        $proteinG = null;
        $micronutrients = [];
        foreach ($nl['nutrients'] ?? [] as $n) {
            $nutrient = $n['nutrient'] ?? null;
            $grams = $n['quantity']['grams'] ?? null;
            if ($nutrient === null || $grams === null) {
                continue;
            }
            if ($nutrient === 'PROTEIN') {
                $proteinG = (float) $grams;
            } elseif (in_array($nutrient, HC_STYLE_NUTRIENT_KEYS, true)) {
                $micronutrients[$nutrient] = (float) $grams;
            }
        }

        $servingAmount = isset($nl['serving']['amount']) ? (float) $nl['serving']['amount'] : 1.0;
        $unitLabel = $nl['serving']['foodMeasurementUnitDisplayName'] ?? 'serving';
        $foodRef = $nl['food'] ?? null;

        // Fetched whenever a food reference exists, regardless of whether
        // gram conversion is possible — brand (present on some, not all,
        // foods — confirmed via real branded items like "Lay's"/"Food Lion")
        // must not be dropped just because a food has no gram serving entry.
        $brandName = null;
        $gramsForEntry = null;
        $gramsPerUnit = null;
        if ($foodRef !== null) {
            $servings = fetchFoodServings($accessToken, $foodRef, $foodResourceCache);
            if ($servings !== null) {
                $brandName = $servings['brand'];
                if ($servingAmount > 0) {
                    $gramsPerUnit = resolveGramsPerUnit($servings, $unitLabel);
                    if ($gramsPerUnit !== null) {
                        $gramsForEntry = $servingAmount * $gramsPerUnit;
                    }
                }
            }
        }

        if ($gramsForEntry !== null && $gramsForEntry > 0) {
            [$foodId, $wasNew, $finalServingAmount, $servingUnitId] = findOrCreateFoodReal(
                $pdo, $userId, $massDimensionId, $name, $brandName, $gramsForEntry, $servingAmount, $unitLabel, $gramsPerUnit,
                $energyKcal, $proteinG, $carbG, $fatG, $micronutrients, $nutrientIds, $gramUnitId
            );
            $matchType = 'real_gram';
            bumpStat('nutrition', 'real_gram_match', 1);
        } else {
            [$foodId, $wasNew, $finalServingAmount, $servingUnitId] = findOrCreateFoodFallback(
                $pdo, $userId, $massDimensionId, $name, $brandName, $energyKcal, $proteinG, $carbG, $fatG,
                $micronutrients, $nutrientIds, $gramUnitId, $fallbackServingUnitCache
            );
            $matchType = 'fallback';
            bumpStat('nutrition', 'fallback_placeholder_match', 1);
        }
        bumpStat('nutrition', $wasNew ? 'foods_db_versions_created' : 'foods_db_versions_reused', 1);

        $apiUid = apiUidFrom($point);
        if ($apiUid === null) {
            bumpStat('nutrition', 'skipped_error', 1);
            return;
        }
        $dataSourceId = findOrCreateDataSource(dataSourceLabel($point), $pdo, $dataSourceIds, $insertDataSourceStmt);

        $action = upsertByNaturalKey(
            $pdo, 'food_log_entries', ['user_id', 'api_uid'], [$userId, $apiUid],
            [
                'start_time' => toMysqlDateTime($nl['interval']['startTime']),
                'end_time' => toMysqlDateTime($nl['interval']['endTime']),
                'meal_type_id' => $mealTypeId,
                'food_id' => $foodId,
                'serving_amount' => $finalServingAmount,
                'serving_unit_id' => $servingUnitId,
                'data_source_id' => $dataSourceId,
                'ingestion_source_id' => $ingestionSource,
            ],
            provenanceNow($userId)
        );
        bumpStat('nutrition', $action, 1);
        debugLog("nutrition api_uid={$apiUid} name=\"{$name}\"" . ($brandName !== null ? " brand=\"{$brandName}\"" : '')
            . " match={$matchType} food_id={$foodId} " . ($wasNew ? 'new_version' : 'existing_version')
            . " serving_amount={$finalServingAmount} action={$action}");
    });

    logLine("Nutrition done: " . json_encode($GLOBALS['runStats']['nutrition'] ?? []));
}

// ----------------------------------------------------------------------------
// 2. Sleep -> sleep_sessions / sleep_stages
// ----------------------------------------------------------------------------

function syncSleep(string $accessToken, PDO $pdo, int $userId, int $ingestionSource, int $mixedIngestionSource, array $sleepTypeIds,
    array $sleepStageTypeIds, array $recordingMethodIds, array &$dataSourceIds, PDOStatement $insertDataSourceStmt, ?DateTimeImmutable $cutoff): void
{
    logLine("--- Sleep (sleep) ---");
    streamDataPoints($accessToken, 'sleep', 'sleep', $cutoff, function (array $point) use (
        $pdo, $userId, $ingestionSource, $mixedIngestionSource, $sleepTypeIds, $sleepStageTypeIds, $recordingMethodIds, &$dataSourceIds, $insertDataSourceStmt
    ) {
        bumpStat('sleep', 'rows_seen', 1);
        $s = $point['sleep'];
        $apiUid = apiUidFrom($point);
        if ($apiUid === null || !isset($s['interval']['startTime'], $s['interval']['endTime'])) {
            bumpStat('sleep', 'skipped_error', 1);
            return;
        }

        $sleepTypeId = $sleepTypeIds[$s['type'] ?? ''] ?? null;
        $recordingMethodId = $recordingMethodIds[$point['dataSource']['recordingMethod'] ?? ''] ?? null;
        $dataSourceId = findOrCreateDataSource(dataSourceLabel($point), $pdo, $dataSourceIds, $insertDataSourceStmt);
        $startTime = toMysqlDateTime($s['interval']['startTime']);

        $action = upsertByNaturalKey(
            $pdo, 'sleep_sessions', ['user_id', 'api_uid'], [$userId, $apiUid],
            [
                'sleep_type_id' => $sleepTypeId,
                'main_sleep' => isset($s['mainSleep']) ? ($s['mainSleep'] ? 1 : 0) : null,
                'start_time' => $startTime,
                'end_time' => toMysqlDateTime($s['interval']['endTime']),
                'data_source_id' => $dataSourceId,
                'recording_method_id' => $recordingMethodId,
                'ingestion_source_id' => $ingestionSource,
            ],
            provenanceNow($userId),
            ['user_id', 'start_time'], [$userId, $startTime], $mixedIngestionSource
        );
        bumpStat('sleep_sessions', $action, 1);
        debugLog("sleep api_uid={$apiUid} start={$s['interval']['startTime']} end={$s['interval']['endTime']} action={$action}");

        // By start_time, not api_uid: a cross-source skip means the actual
        // row belongs to Health Connect under its own uuid, not this one.
        $findSession = $pdo->prepare("SELECT id FROM sleep_sessions WHERE user_id = ? AND start_time = ?");
        $findSession->execute([$userId, $startTime]);
        $sessionId = (int) $findSession->fetchColumn();
        if ($sessionId === 0) {
            return;
        }

        // IGNORE, not a plain INSERT: uq_sleep_stages_natural is keyed on
        // (session, stage_type, start_time) - not end_time - so a stage
        // whose end_time drifts slightly between sources (the same rounding
        // difference already seen on the parent session) would slip past an
        // in-memory (start_time, end_time) check and crash on the real
        // constraint. Found via a real cross-source sleep sync.
        $insertStage = $pdo->prepare(
            "INSERT IGNORE INTO sleep_stages (user_id, sleep_session_id, stage_type_id, start_time, end_time, ingestion_source_id)
             VALUES (?, ?, ?, ?, ?, ?)"
        );
        foreach ($s['stages'] ?? [] as $stage) {
            if (!isset($stage['startTime'], $stage['endTime'], $stage['type'])) {
                continue;
            }
            $stageTypeId = $sleepStageTypeIds[$stage['type']] ?? null;
            if ($stageTypeId === null) {
                bumpStat('sleep_stages', 'skipped_unmapped', 1);
                continue;
            }
            $startTime = toMysqlDateTime($stage['startTime']);
            $endTime = toMysqlDateTime($stage['endTime']);
            $insertStage->execute([$userId, $sessionId, $stageTypeId, $startTime, $endTime, $ingestionSource]);
            bumpStat('sleep_stages', $insertStage->rowCount() > 0 ? 'inserted' : 'skipped_duplicate', 1);
        }
        debugLog("sleep_stages session_id={$sessionId} stages_seen=" . count($s['stages'] ?? []));
    });
}

// ----------------------------------------------------------------------------
// 3. Exercise -> exercise_sessions
// ----------------------------------------------------------------------------

function parseSecondsSuffix(?string $value): ?int
{
    if ($value === null) {
        return null;
    }
    return (int) round(((float) rtrim($value, 's')) * 1000);
}

function syncExercise(string $accessToken, PDO $pdo, int $userId, int $ingestionSource, int $mixedIngestionSource, int $meterUnitId,
    array $recordingMethodIds, array &$dataSourceIds, PDOStatement $insertDataSourceStmt,
    array &$activityTypeIds, PDOStatement $insertActivityTypeStmt, ?DateTimeImmutable $cutoff): void
{
    logLine("--- Exercise (exercise) ---");
    streamDataPoints($accessToken, 'exercise', 'exercise', $cutoff, function (array $point) use (
        $pdo, $userId, $ingestionSource, $mixedIngestionSource, $meterUnitId, $recordingMethodIds, &$dataSourceIds, $insertDataSourceStmt,
        &$activityTypeIds, $insertActivityTypeStmt
    ) {
        bumpStat('exercise', 'rows_seen', 1);
        $e = $point['exercise'];
        $apiUid = apiUidFrom($point);
        if ($apiUid === null || !isset($e['interval']['startTime'])) {
            bumpStat('exercise', 'skipped_error', 1);
            return;
        }

        $startTime = toMysqlDateTime($e['interval']['startTime']);
        $endTime = isset($e['interval']['endTime']) ? toMysqlDateTime($e['interval']['endTime']) : null;
        $durationMs = $endTime !== null
            ? (int) round((strtotime($endTime) - strtotime($startTime)) * 1000)
            : null;

        $activityTypeId = findOrCreateActivityType(
            isset($e['exerciseType']) ? 'API_' . $e['exerciseType'] : null,
            $pdo, $activityTypeIds, $insertActivityTypeStmt
        );
        $dataSourceId = findOrCreateDataSource(dataSourceLabel($point), $pdo, $dataSourceIds, $insertDataSourceStmt);
        $recordingMethodId = $recordingMethodIds[$point['dataSource']['recordingMethod'] ?? ''] ?? null;

        $summary = $e['metricsSummary'] ?? [];
        $rawDetails = array_filter([
            'heartRateZoneDurations' => $summary['heartRateZoneDurations'] ?? null,
            'activeZoneMinutes' => $summary['activeZoneMinutes'] ?? null,
            'mobilityMetrics' => $summary['mobilityMetrics'] ?? null,
            'exerciseEvents' => $e['exerciseEvents'] ?? null,
        ], fn($v) => $v !== null);

        $action = upsertByNaturalKey(
            $pdo, 'exercise_sessions', ['user_id', 'api_uid'], [$userId, $apiUid],
            [
                'start_time' => $startTime,
                'end_time' => $endTime,
                'activity_name' => $e['displayName'] ?? null,
                'activity_type_id' => $activityTypeId,
                'duration_ms' => $durationMs,
                'active_duration_ms' => parseSecondsSuffix($e['activeDuration'] ?? null),
                'calories' => isset($summary['caloriesKcal']) ? (int) round((float) $summary['caloriesKcal']) : null,
                'distance' => isset($summary['distanceMillimeters']) ? ((float) $summary['distanceMillimeters'] / 1000) : null,
                'distance_unit_id' => isset($summary['distanceMillimeters']) ? $meterUnitId : null,
                'steps' => isset($summary['steps']) ? (int) $summary['steps'] : null,
                'average_heart_rate' => isset($summary['averageHeartRateBeatsPerMinute']) ? (int) $summary['averageHeartRateBeatsPerMinute'] : null,
                'has_gps' => !empty($e['exerciseMetadata']['hasGps']) ? 1 : 0,
                'data_source_id' => $dataSourceId,
                'recording_method_id' => $recordingMethodId,
                'ingestion_source_id' => $ingestionSource,
                'raw_details' => empty($rawDetails) ? null : json_encode($rawDetails),
            ],
            provenanceNow($userId),
            ['user_id', 'start_time'], [$userId, $startTime], $mixedIngestionSource
        );
        bumpStat('exercise', $action, 1);
        debugLog("exercise api_uid={$apiUid} activity=\"" . ($e['displayName'] ?? $e['exerciseType'] ?? '?') . "\" action={$action}");
    });
}

// ----------------------------------------------------------------------------
// 4 & 5. Weight & height -> measurements
// ----------------------------------------------------------------------------

function syncMeasurement(string $accessToken, PDO $pdo, string $dataType, string $bodyKey, string $valueField,
    int $userId, int $ingestionSource, int $mixedIngestionSource, int $measurementTypeId, int $unitId, array $recordingMethodIds,
    array &$dataSourceIds, PDOStatement $insertDataSourceStmt, ?DateTimeImmutable $cutoff): void
{
    logLine("--- {$dataType} ({$dataType}) ---");
    streamDataPoints($accessToken, $dataType, $bodyKey, $cutoff, function (array $point) use (
        $pdo, $bodyKey, $valueField, $userId, $ingestionSource, $mixedIngestionSource, $measurementTypeId, $unitId,
        $recordingMethodIds, &$dataSourceIds, $insertDataSourceStmt, $dataType
    ) {
        bumpStat($dataType, 'rows_seen', 1);
        $body = $point[$bodyKey];
        $apiUid = apiUidFrom($point);
        if ($apiUid === null || !isset($body['sampleTime']['physicalTime'], $body[$valueField])) {
            bumpStat($dataType, 'skipped_error', 1);
            return;
        }

        $dataSourceId = findOrCreateDataSource(dataSourceLabel($point), $pdo, $dataSourceIds, $insertDataSourceStmt);
        $recordingMethodId = $recordingMethodIds[$point['dataSource']['recordingMethod'] ?? ''] ?? null;

        $readingTime = toMysqlDateTime($body['sampleTime']['physicalTime']);

        $action = upsertByNaturalKey(
            $pdo, 'measurements', ['user_id', 'measurement_type_id', 'api_uid'], [$userId, $measurementTypeId, $apiUid],
            [
                'reading_time' => $readingTime,
                'value' => (float) $body[$valueField],
                'unit_id' => $unitId,
                'data_source_id' => $dataSourceId,
                'recording_method_id' => $recordingMethodId,
                'ingestion_source_id' => $ingestionSource,
            ],
            provenanceNow($userId),
            ['user_id', 'measurement_type_id', 'reading_time'], [$userId, $measurementTypeId, $readingTime], $mixedIngestionSource
        );
        bumpStat($dataType, $action, 1);
        debugLog("{$dataType} api_uid={$apiUid} value={$body[$valueField]} action={$action}");
    });
}

// ----------------------------------------------------------------------------
// 6. Daily resting heart rate -> daily_resting_heart_rate
// ----------------------------------------------------------------------------

function syncDailyRestingHeartRate(string $accessToken, PDO $pdo, int $userId, int $ingestionSource,
    array $recordingMethodIds, array $calcMethodIds, array &$dataSourceIds, PDOStatement $insertDataSourceStmt, ?DateTimeImmutable $cutoff): void
{
    logLine("--- Daily resting heart rate (daily-resting-heart-rate) ---");
    streamDataPoints($accessToken, 'daily-resting-heart-rate', 'dailyRestingHeartRate', $cutoff, function (array $point) use (
        $pdo, $userId, $ingestionSource, $recordingMethodIds, $calcMethodIds, &$dataSourceIds, $insertDataSourceStmt
    ) {
        bumpStat('daily_resting_heart_rate', 'rows_seen', 1);
        $d = $point['dailyRestingHeartRate'];
        if (!isset($d['date'], $d['beatsPerMinute'])) {
            bumpStat('daily_resting_heart_rate', 'skipped_error', 1);
            return;
        }

        $dataSourceId = findOrCreateDataSource(dataSourceLabel($point), $pdo, $dataSourceIds, $insertDataSourceStmt);
        $recordingMethodId = $recordingMethodIds[$point['dataSource']['recordingMethod'] ?? ''] ?? null;
        $calcMethodId = $calcMethodIds[$d['dailyRestingHeartRateMetadata']['calculationMethod'] ?? ''] ?? null;

        $action = upsertByNaturalKey(
            $pdo, 'daily_resting_heart_rate', ['user_id', 'reading_date'], [$userId, civilDate($d['date'])],
            [
                'bpm' => (int) $d['beatsPerMinute'],
                'calculation_method_id' => $calcMethodId,
                'data_source_id' => $dataSourceId,
                'recording_method_id' => $recordingMethodId,
                'ingestion_source_id' => $ingestionSource,
            ],
            provenanceNow($userId)
        );
        bumpStat('daily_resting_heart_rate', $action, 1);
        debugLog("daily_resting_heart_rate date=" . civilDate($d['date']) . " bpm={$d['beatsPerMinute']} action={$action}");
    });
}

// ----------------------------------------------------------------------------
// 7, 8, 9. Steps, heart rate, HRV -> insert-missing (no native ID available)
// ----------------------------------------------------------------------------

function existingTimestamps(PDO $pdo, string $table, int $userId, ?DateTimeImmutable $cutoff): array
{
    if ($cutoff === null) {
        // Full mode: scanning the entire table's timestamps into memory isn't
        // safe at HC-import scale (millions of rows) — full mode for these
        // three types relies on the caller re-running incrementally instead.
        return [];
    }
    $stmt = $pdo->prepare("SELECT reading_time FROM {$table} WHERE user_id = ? AND reading_time >= ?");
    $stmt->execute([$userId, $cutoff->format('Y-m-d H:i:s')]);
    $set = [];
    foreach ($stmt as $row) {
        $set[$row['reading_time']] = true;
    }
    return $set;
}

function syncInsertMissingSeries(string $accessToken, PDO $pdo, string $dataType, string $bodyKey, string $table,
    string $valueField, string $valueColumn, int $userId, int $ingestionSource, array $recordingMethodIds,
    array &$dataSourceIds, PDOStatement $insertDataSourceStmt, ?DateTimeImmutable $cutoff): void
{
    logLine("--- {$dataType} ({$dataType}) ---");
    $seen = existingTimestamps($pdo, $table, $userId, $cutoff);
    logLine(count($seen) . " existing {$table} timestamps loaded for dedup" . ($cutoff === null ? " (full mode: dedup skipped, expect re-run incrementally instead)" : ""));

    // IGNORE, not a plain INSERT: full-mode runs deliberately skip the
    // in-memory $seen preload above, so this is the only guard against a
    // real DB-level unique constraint (e.g. heart_rate_readings' natural
    // (user_id, reading_time) key) rejecting a reading this same run's HC
    // import already inserted for the identical timestamp. Found via a real
    // --full run crashing on exactly that overlap.
    $insert = $pdo->prepare(
        "INSERT IGNORE INTO {$table} (user_id, reading_time, {$valueColumn}, data_source_id, recording_method_id, ingestion_source_id)
         VALUES (?, ?, ?, ?, ?, ?)"
    );

    $pageInserted = 0;
    $pageSkipped = 0;

    streamDataPoints($accessToken, $dataType, $bodyKey, $cutoff, function (array $point) use (
        $pdo, $bodyKey, $valueField, &$seen, $insert, $userId, $ingestionSource, $recordingMethodIds,
        &$dataSourceIds, $insertDataSourceStmt, $dataType, &$pageInserted, &$pageSkipped
    ) {
        bumpStat($dataType, 'rows_seen', 1);
        $body = $point[$bodyKey];
        $timeIso = $body['interval']['startTime'] ?? $body['sampleTime']['physicalTime'] ?? null;
        if ($timeIso === null || !isset($body[$valueField])) {
            bumpStat($dataType, 'skipped_error', 1);
            return;
        }
        $readingTime = toMysqlDateTime($timeIso);
        if (isset($seen[$readingTime])) {
            bumpStat($dataType, 'skipped_duplicate', 1);
            $pageSkipped++;
            return;
        }
        $seen[$readingTime] = true;

        $dataSourceId = findOrCreateDataSource(dataSourceLabel($point), $pdo, $dataSourceIds, $insertDataSourceStmt);
        $recordingMethodId = $recordingMethodIds[$point['dataSource']['recordingMethod'] ?? ''] ?? null;

        $rawValue = $body[$valueField];
        $value = ($dataType === 'heart-rate-variability') ? (float) $rawValue : (int) round((float) $rawValue);

        $insert->execute([$userId, $readingTime, $value, $dataSourceId, $recordingMethodId, $ingestionSource]);
        if ($insert->rowCount() > 0) {
            bumpStat($dataType, 'inserted', 1);
            $pageInserted++;
        } else {
            bumpStat($dataType, 'skipped_duplicate', 1);
            $pageSkipped++;
        }
    }, function (int $page, int $pointCount) use ($dataType, &$pageInserted, &$pageSkipped) {
        // Per-page, not per-row — a full day/year of steps/heart-rate/HRV can
        // be tens of thousands of rows, too many to trace individually.
        debugLog("{$dataType} page={$page} points={$pointCount} inserted={$pageInserted} skipped={$pageSkipped}");
        $pageInserted = 0;
        $pageSkipped = 0;
    });
}

// ----------------------------------------------------------------------------
// Run
// ----------------------------------------------------------------------------

syncNutrition($accessToken, $pdo, $userId, $ingestionSourceApi, $massDimensionId, $gramUnitId, $mealTypeIds, $nutrientIds, $dataSourceIds, $insertDataSource, $cutoff);
syncSleep($accessToken, $pdo, $userId, $ingestionSourceApi, $ingestionSourceMixed, $sleepTypeIds, $sleepStageTypeIds, $recordingMethodIds, $dataSourceIds, $insertDataSource, $cutoff);
syncExercise($accessToken, $pdo, $userId, $ingestionSourceApi, $ingestionSourceMixed, $meterUnitId, $recordingMethodIds, $dataSourceIds, $insertDataSource, $activityTypeIds, $insertActivityType, $cutoff);
syncMeasurement($accessToken, $pdo, 'weight', 'weight', 'weightGrams', $userId, $ingestionSourceApi, $ingestionSourceMixed, $measurementTypeIds['weight'], $gramUnitId, $recordingMethodIds, $dataSourceIds, $insertDataSource, $cutoff);
syncMeasurement($accessToken, $pdo, 'height', 'height', 'heightMillimeters', $userId, $ingestionSourceApi, $ingestionSourceMixed, $measurementTypeIds['height'], $mmUnitId, $recordingMethodIds, $dataSourceIds, $insertDataSource, $cutoff);
syncDailyRestingHeartRate($accessToken, $pdo, $userId, $ingestionSourceApi, $recordingMethodIds, $calcMethodIds, $dataSourceIds, $insertDataSource, $cutoff);
syncInsertMissingSeries($accessToken, $pdo, 'steps', 'steps', 'steps_readings', 'count', 'steps', $userId, $ingestionSourceApi, $recordingMethodIds, $dataSourceIds, $insertDataSource, $cutoff);
syncInsertMissingSeries($accessToken, $pdo, 'heart-rate', 'heartRate', 'heart_rate_readings', 'beatsPerMinute', 'bpm', $userId, $ingestionSourceApi, $recordingMethodIds, $dataSourceIds, $insertDataSource, $cutoff);
syncInsertMissingSeries($accessToken, $pdo, 'heart-rate-variability', 'heartRateVariability', 'heart_rate_variability_readings', 'rootMeanSquareOfSuccessiveDifferencesMilliseconds', 'rmssd_ms', $userId, $ingestionSourceApi, $recordingMethodIds, $dataSourceIds, $insertDataSource, $cutoff);

$elapsed = round(microtime(true) - $startedAt, 1);
logLine("=== Sync complete in {$elapsed}s ===");
foreach ($runStats as $category => $stats) {
    logLine(strtoupper($category) . ': ' . json_encode($stats));
}

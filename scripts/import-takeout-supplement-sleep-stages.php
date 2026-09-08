<?php

declare(strict_types=1);

// One-time supplemental pass: re-processes UserSleepStages_*.csv now that
// lut_sleep_stage_type has been extended with ASLEEP/RESTLESS/UNSPECIFIED
// (the CLASSIC-mode vocabulary, discovered mid-import — see
// doc/wiki/Database-Schema.md). Safe to re-run against already-imported
// data: every row already present is skipped via INSERT IGNORE on the
// (user_id, sleep_stage_id) and (user_id, fingerprint) unique keys: only
// the previously-dropped rows get inserted this time.
//
// Usage: php scripts/import-takeout-supplement-sleep-stages.php <path-to-takeout.zip>

require __DIR__ . '/../src/Env.php';
require __DIR__ . '/../src/Database.php';

Env::load(__DIR__ . '/../.env');

$zipPath = $argv[1] ?? null;
if ($zipPath === null || !is_file($zipPath)) {
    fwrite(STDERR, "Usage: php import-takeout-supplement-sleep-stages.php <path-to-takeout.zip>\n");
    exit(1);
}

$logDir = __DIR__ . '/../storage/import-logs';
$logPath = $logDir . '/takeout-import-supplement-sleep-stages-' . date('Ymd-His') . '.log';
$logFile = fopen($logPath, 'w');

function logLine(string $message): void
{
    global $logFile;
    $line = '[' . date('Y-m-d H:i:s') . '] ' . $message;
    echo $line . "\n";
    fwrite($logFile, $line . "\n");
}

function isoToMysql(string $iso): string
{
    $dt = new DateTimeImmutable($iso);
    return $dt->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s');
}

function fp(array $parts): string
{
    return hash('sha256', implode('|', $parts));
}

function openZipLines(ZipArchive $zip, string $entry, bool $skipHeader = false)
{
    $stream = $zip->getStream($entry);
    if ($stream === false) {
        throw new RuntimeException("Could not open zip entry: {$entry}");
    }
    if ($skipHeader) {
        fgets($stream);
    }
    while (($line = fgets($stream)) !== false) {
        yield rtrim($line, "\r\n");
    }
    fclose($stream);
}

function zipEntriesMatching(ZipArchive $zip, string $pattern): array
{
    $matches = [];
    for ($i = 0; $i < $zip->numFiles; $i++) {
        $name = $zip->getNameIndex($i);
        if ($name !== false && fnmatch($pattern, $name)) {
            $matches[] = $name;
        }
    }
    sort($matches);
    return $matches;
}

logLine("=== Sleep stages supplemental pass starting ===");

$pdo = Database::connect();
$ingestionSourceTakeout = (int) $pdo->query("SELECT id FROM lut_ingestion_source WHERE name='google_takeout'")->fetchColumn();
$userId = 2;

$sleepStageTypeIds = [];
foreach ($pdo->query("SELECT id, name FROM lut_sleep_stage_type") as $row) {
    $sleepStageTypeIds[$row['name']] = (int) $row['id'];
}
logLine("Sleep stage types now available: " . implode(', ', array_keys($sleepStageTypeIds)));

$sleepIdToRowId = [];
foreach ($pdo->query("SELECT id, sleep_id FROM sleep_sessions") as $row) {
    $sleepIdToRowId[$row['sleep_id']] = (int) $row['id'];
}
logLine("Loaded " . count($sleepIdToRowId) . " existing sleep sessions");

$beforeCount = (int) $pdo->query("SELECT COUNT(*) FROM sleep_stages")->fetchColumn();

$zip = new ZipArchive();
if ($zip->open($zipPath) !== true) {
    logLine("FATAL: could not open zip file");
    exit(1);
}

$root = 'Takeout/Google Health/';
$entries = zipEntriesMatching($zip, $root . 'Health Fitness Data_GoogleData/UserSleepStages_*.csv');
logLine("Processing " . count($entries) . " UserSleepStages files");

$rowsSeen = 0;
$inserted = 0;
$skippedError = 0;
$skippedDuplicate = 0;

$insert = $pdo->prepare(
    "INSERT IGNORE INTO sleep_stages (user_id, sleep_session_id, sleep_stage_id, stage_type_id, start_time, end_time, ingestion_source_id, fingerprint)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
);

foreach ($entries as $entry) {
    logLine("--- {$entry} ---");
    foreach (openZipLines($zip, $entry, true) as $line) {
        if ($line === '') {
            continue;
        }
        $row = str_getcsv($line);
        [$sleepId, $stageId, $stageType, $startOffset, $stageStart, $endOffset, $stageEnd] = array_pad($row, 7, null);
        $rowsSeen++;
        try {
            $sessionRowId = $sleepIdToRowId[$sleepId] ?? null;
            if ($sessionRowId === null) {
                logLine("WARN sleep stage {$stageId}: parent sleep session {$sleepId} not found, skipping");
                $skippedError++;
                continue;
            }
            $stageTypeId = $sleepStageTypeIds[$stageType] ?? null;
            if ($stageTypeId === null) {
                logLine("WARN sleep stage {$stageId}: STILL unknown stage type '{$stageType}' after supplement, skipping");
                $skippedError++;
                continue;
            }
            $startTime = isoToMysql($stageStart);
            $endTime = isoToMysql($stageEnd);
            $fingerprint = fp([$sessionRowId, $startTime, $endTime, $stageType]);
            $insert->execute([$userId, $sessionRowId, $stageId, $stageTypeId, $startTime, $endTime, $ingestionSourceTakeout, $fingerprint]);
            if ($insert->rowCount() > 0) {
                $inserted++;
            } else {
                $skippedDuplicate++;
            }
        } catch (Throwable $e) {
            logLine("ERROR sleep stage {$stageId}: " . $e->getMessage());
            $skippedError++;
        }
    }
}
$zip->close();

$afterCount = (int) $pdo->query("SELECT COUNT(*) FROM sleep_stages")->fetchColumn();

logLine("=== Supplement complete ===");
logLine("rows_seen={$rowsSeen}, newly_inserted={$inserted}, skipped_duplicate={$skippedDuplicate}, skipped_error={$skippedError}");
logLine("sleep_stages count before={$beforeCount}, after={$afterCount}, net_change=" . ($afterCount - $beforeCount));

fclose($logFile);

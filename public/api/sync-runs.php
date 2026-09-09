<?php

declare(strict_types=1);

// GET /api/sync-runs.php
// Lists prior sync runs that have a recorded API log (storage/api-logs/<run_id>/),
// newest first, for populating a "replay" picker in the UI. Only runs with
// a manifest.json are listed (a run started with --no-log has nothing to
// replay from). Each run is enriched with its actual duration and covered
// date window by reading its human-readable log
// (storage/import-logs/sync-google-health-<run_id>.log) - a replay run
// never writes its own api-log manifest (see sync-google-health.php), so
// every directory here corresponds 1:1 with an original live run's own log.

require_once __DIR__ . '/../../src/Env.php';

Env::load(__DIR__ . '/../../.env');
header('Content-Type: application/json');

$logsDir = __DIR__ . '/../../storage/api-logs';
$importLogsDir = __DIR__ . '/../../storage/import-logs';

$runs = [];
if (is_dir($logsDir)) {
    foreach (scandir($logsDir) as $entry) {
        if ($entry === '.' || $entry === '..') {
            continue;
        }
        $runDir = $logsDir . '/' . $entry;
        $manifestPath = $runDir . '/manifest.json';
        if (!is_dir($runDir) || !is_file($manifestPath)) {
            continue;
        }
        $manifest = json_decode((string) file_get_contents($manifestPath), true);
        if (!is_array($manifest)) {
            continue;
        }

        $isFull = $manifest['isFull'] ?? null;
        $days = $manifest['days'] ?? null;
        $startedAt = $manifest['startedAt'] ?? null;

        $durationSeconds = null;
        $humanLogPath = $importLogsDir . '/sync-google-health-' . $entry . '.log';
        if (is_file($humanLogPath)) {
            $contents = file_get_contents($humanLogPath);
            if ($contents !== false && preg_match('/complete in ([\d.]+)s/', $contents, $m)) {
                $durationSeconds = (float) $m[1];
            }
        }

        if ($isFull) {
            $window = 'Full history';
        } elseif ($days !== null && $startedAt !== null) {
            try {
                $end = new DateTimeImmutable($startedAt);
                $start = $end->modify("-{$days} days");
                $window = "Last {$days}d (covers {$start->format('Y-m-d')} to {$end->format('Y-m-d')})";
            } catch (Exception $e) {
                $window = "Last {$days} day(s)";
            }
        } else {
            $window = 'Unknown window';
        }

        $runs[] = [
            'runId' => $entry,
            'isFull' => $isFull,
            'days' => $days,
            'startedAt' => $startedAt,
            'window' => $window,
            'durationSeconds' => $durationSeconds,
        ];
    }
}

usort($runs, static fn($a, $b) => strcmp($b['runId'], $a['runId']));

echo json_encode(['runs' => $runs]);

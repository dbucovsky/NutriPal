<?php

declare(strict_types=1);

// POST /api/run-sync.php
// Body: {"mode": "live"|"replay", "days"?: int, "full"?: bool, "replayRunId"?: string, "debug"?: bool}
//
// Runs scripts/sync-google-health.php synchronously (this request blocks
// until the script exits) and returns its captured output. Deliberately
// simple for now — no background job/polling — since this is triggered
// occasionally from a local admin UI, not a routine high-frequency action.
// A live incremental sync takes seconds; --full could take much longer,
// which is why the dev server is started with unlimited execution time
// (see start-services.ps1).

require_once __DIR__ . '/../../src/Env.php';

Env::load(__DIR__ . '/../../.env');
header('Content-Type: application/json');
set_time_limit(0);

$input = json_decode(file_get_contents('php://input') ?: '', true);
if (!is_array($input)) {
    http_response_code(400);
    echo json_encode(['error' => 'invalid JSON body']);
    exit;
}

$mode = $input['mode'] ?? '';
if (!in_array($mode, ['live', 'replay'], true)) {
    http_response_code(400);
    echo json_encode(['error' => 'mode must be "live" or "replay"']);
    exit;
}

$args = [];

if ($mode === 'replay') {
    $runId = (string) ($input['replayRunId'] ?? '');
    if (!preg_match('/^[A-Za-z0-9_-]+$/', $runId)) {
        http_response_code(400);
        echo json_encode(['error' => 'replayRunId is required and must look like a run id']);
        exit;
    }
    $args[] = '--replay=' . $runId;
} elseif (!empty($input['full'])) {
    $args[] = '--full';
} elseif (isset($input['days'])) {
    $days = (int) $input['days'];
    if ($days < 1 || $days > 3650) {
        http_response_code(400);
        echo json_encode(['error' => 'days must be between 1 and 3650']);
        exit;
    }
    $args[] = '--days=' . $days;
}

if (!empty($input['debug'])) {
    $args[] = '--debug';
}

$scriptPath = escapeshellarg(__DIR__ . '/../../scripts/sync-google-health.php');
$argString = implode(' ', array_map('escapeshellarg', $args));
$command = escapeshellarg(PHP_BINARY) . ' ' . $scriptPath . ' ' . $argString . ' 2>&1';

$output = [];
$exitCode = 0;
exec($command, $output, $exitCode);

echo json_encode([
    'success' => $exitCode === 0,
    'exitCode' => $exitCode,
    'output' => implode("\n", $output),
]);

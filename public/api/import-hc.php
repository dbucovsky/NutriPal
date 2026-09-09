<?php

declare(strict_types=1);

// POST /api/import-hc.php
// Body: {"path": "C:\\path\\to\\health_connect_export.db"}
//
// Runs scripts/import-health-connect.php synchronously against a Health
// Connect export file that is already on disk (same positional-argument
// usage as the CLI script). Deliberately NOT a browser upload: a real
// export is ~500MB, and PHP's built-in dev server (php -S, used by
// start-services.ps1) buffers the entire multipart body before the script
// even runs, which made a real upload take tens of minutes for a transfer
// that should be instant on localhost — a limitation of the dev server
// SAPI, not something worth working around. Passing a path is also just
// how every other HC-import path in this project already works.

require_once __DIR__ . '/../../src/Env.php';

Env::load(__DIR__ . '/../../.env');
header('Content-Type: application/json');
set_time_limit(0);

$input = json_decode(file_get_contents('php://input') ?: '', true);
$path = is_array($input) ? ($input['path'] ?? '') : '';

if ($path === '' || !is_file($path)) {
    http_response_code(400);
    echo json_encode(['error' => 'path must point to an existing file']);
    exit;
}

$header = file_get_contents($path, false, null, 0, 16);
if ($header === false || !str_starts_with($header, "SQLite format 3\0")) {
    http_response_code(400);
    echo json_encode(['error' => 'file is not a SQLite database (expected the Health Connect export .db file)']);
    exit;
}

$scriptPath = escapeshellarg(__DIR__ . '/../../scripts/import-health-connect.php');
$command = escapeshellarg(PHP_BINARY) . ' ' . $scriptPath . ' ' . escapeshellarg($path) . ' 2>&1';

$output = [];
$exitCode = 0;
exec($command, $output, $exitCode);

echo json_encode([
    'success' => $exitCode === 0,
    'exitCode' => $exitCode,
    'output' => implode("\n", $output),
]);

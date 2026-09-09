<?php

declare(strict_types=1);

// GET /api/sync-progress.php?type=sync|import
//
// Called once, right when the Sync tab starts a live sync/replay/import
// (before firing the actual blocking run-sync.php/import-hc.php request),
// to get a rough "how long did this kind of run take last time" estimate.
//
// Deliberately NOT polled during the run: PHP's built-in dev server
// (php -S, what start-services.ps1 runs) is single-threaded, so it can't
// serve this endpoint while it's still busy with the blocking request -
// confirmed directly (a request sent here mid-import just queued for the
// entire ~3 minutes and only returned once the import finished). A live
// progress tail would need a second dedicated server process to work
// locally; not worth that permanent complexity for this.

require_once __DIR__ . '/../../src/Env.php';

Env::load(__DIR__ . '/../../.env');
header('Content-Type: application/json');

$type = $_GET['type'] ?? '';
$pattern = match ($type) {
    'sync' => 'sync-google-health-*.log',
    'import' => 'health-connect-import-*.log',
    default => null,
};
if ($pattern === null) {
    http_response_code(400);
    echo json_encode(['error' => 'type must be "sync" or "import"']);
    exit;
}

$logDir = __DIR__ . '/../../storage/import-logs';
$files = glob($logDir . '/' . $pattern) ?: [];
usort($files, static fn($a, $b) => filemtime($b) <=> filemtime($a));

$estimatedSeconds = null;
foreach ($files as $file) {
    $contents = file_get_contents($file);
    if ($contents !== false && preg_match('/complete in ([\d.]+)s/', $contents, $m)) {
        $estimatedSeconds = (float) $m[1];
        break;
    }
}

echo json_encode(['estimatedSeconds' => $estimatedSeconds]);

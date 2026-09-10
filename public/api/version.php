<?php

declare(strict_types=1);

// GET /api/version.php
// Returns the current app version by reading the top of CHANGELOG.md,
// rather than hardcoding a version string in the frontend that would
// silently go stale the next time CHANGELOG.md is bumped.

header('Content-Type: application/json');

$changelogPath = __DIR__ . '/../../CHANGELOG.md';
$version = null;

$handle = fopen($changelogPath, 'r');
if ($handle !== false) {
    while (($line = fgets($handle)) !== false) {
        if (preg_match('/^##\s*(V\d+\.\d+\.\d+)/', $line, $m)) {
            $version = $m[1];
            break;
        }
    }
    fclose($handle);
}

echo json_encode(['version' => $version]);

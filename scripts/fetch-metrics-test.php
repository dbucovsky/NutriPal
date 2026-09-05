<?php

declare(strict_types=1);

/**
 * Exploratory CLI script: probes a set of candidate Google Health data types
 * (activity, vitals/heart rate, sleep, weight/height) to see what's actually
 * populated in this account before deciding what to build out fully.
 *
 * Requires the stored refresh token to already carry the expanded scopes
 * (activity_and_fitness, health_metrics_and_measurements, sleep) — re-run
 * auth-login.php first if the token predates the scope expansion.
 *
 * Not part of the app's request flow. Usage: php scripts/fetch-metrics-test.php
 */

require_once __DIR__ . '/../src/Env.php';
require_once __DIR__ . '/../src/GoogleOAuth.php';
require_once __DIR__ . '/../src/TokenStore.php';

Env::load(__DIR__ . '/../.env');

$tokenStore = new TokenStore(__DIR__ . '/../storage/google-tokens.json');
$tokens = $tokenStore->load();

if ($tokens === null || !isset($tokens['refresh_token'])) {
    fwrite(STDERR, "No stored tokens with a refresh_token. Run the OAuth flow (auth-login.php) first.\n");
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

fwrite(STDOUT, "Granted scope(s):\n  " . ($refreshed['scope'] ?? '(not returned)') . "\n\n");

$candidates = [
    // Activity & fitness
    'steps', 'distance', 'active-minutes', 'active-zone-minutes',
    'exercise', 'floors', 'active-energy-burned', 'total-calories',
    // Heart rate & vitals
    'heart-rate', 'heart-rate-variability', 'daily-resting-heart-rate',
    'vo2-max', 'oxygen-saturation', 'blood-glucose', 'body-fat',
    // Sleep
    'sleep',
    // Weight & height
    'weight', 'height',
];

function fetchDataType(string $accessToken, string $dataType, int $pageSize = 50): array
{
    $url = 'https://health.googleapis.com/v4/users/me/dataTypes/' . $dataType . '/dataPoints?'
        . http_build_query(['pageSize' => $pageSize]);

    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $accessToken,
            'Accept: application/json',
        ],
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 20,
    ]);

    $body = curl_exec($ch);
    $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    return ['status' => $status, 'body' => $body];
}

$debugDir = __DIR__ . '/../storage/debug-metrics';
if (!is_dir($debugDir)) {
    mkdir($debugDir, 0700, true);
}

fwrite(STDOUT, str_pad('Data type', 26) . str_pad('HTTP', 6) . "Result\n");
fwrite(STDOUT, str_repeat('-', 60) . "\n");

foreach ($candidates as $dataType) {
    $result = fetchDataType($accessToken, $dataType);
    $decoded = json_decode($result['body'], true);

    file_put_contents(
        $debugDir . '/' . $dataType . '.json',
        json_encode($decoded ?? $result['body'], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)
    );

    $line = str_pad($dataType, 26) . str_pad((string) $result['status'], 6);

    if ($result['status'] !== 200) {
        $message = is_array($decoded) ? ($decoded['error']['message'] ?? 'error') : 'error';
        $line .= "FAILED: {$message}";
    } else {
        $points = $decoded['dataPoints'] ?? [];
        $count = count($points);
        $line .= $count > 0 ? "{$count} point(s) returned" : 'no data (0 points)';
    }

    fwrite(STDOUT, $line . "\n");
}

fwrite(STDOUT, "\nFull raw responses saved per type in: {$debugDir}\n");

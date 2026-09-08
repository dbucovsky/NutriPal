<?php

declare(strict_types=1);

/**
 * Exploratory CLI script: fetches the last N days of every relevant Google
 * Health data type from the LIVE API and writes the raw responses to a
 * temp JSON file (not the database) so they can be diffed against what's
 * already in the DB from the Health Connect bulk import, as a real-world
 * cross-source consistency check. Not part of the app's request flow.
 *
 * Usage: php scripts/fetch-recent-compare.php [days] [output-path]
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

$days = isset($argv[1]) ? (int) $argv[1] : 10;
$outputPath = $argv[2] ?? (__DIR__ . '/../storage/debug-metrics/recent-compare-' . $days . 'days.json');
$cutoff = (new DateTimeImmutable('today', new DateTimeZone('UTC')))->modify("-{$days} days");

function fetchPage(string $accessToken, string $dataType, ?string $pageToken, int $pageSize = 500): array
{
    $params = ['pageSize' => $pageSize];
    if ($pageToken !== null) {
        $params['pageToken'] = $pageToken;
    }
    $url = 'https://health.googleapis.com/v4/users/me/dataTypes/' . $dataType . '/dataPoints?' . http_build_query($params);

    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_HTTPHEADER => ['Authorization: Bearer ' . $accessToken, 'Accept: application/json'],
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 30,
    ]);
    $body = curl_exec($ch);
    if ($body === false) {
        fwrite(STDERR, "cURL error on {$dataType}: " . curl_error($ch) . "\n");
        return ['dataPoints' => []];
    }
    $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($status !== 200) {
        fwrite(STDERR, "HTTP {$status} on {$dataType}: {$body}\n");
        return ['dataPoints' => []];
    }
    return json_decode($body, true) ?? ['dataPoints' => []];
}

function civilDateFrom(array $date): DateTimeImmutable
{
    return new DateTimeImmutable(sprintf('%04d-%02d-%02d', $date['year'], $date['month'], $date['day']));
}

/** Pulls the best-available date out of a data point for a given type, for client-side cutoff filtering. */
function pointDate(string $dataType, array $point): ?DateTimeImmutable
{
    $body = $point[str_replace('-', '', lcfirstCamel($dataType))] ?? null;
    // Fallback: the JSON key for each type is camelCase of the dash-separated dataType name.
    if ($body === null) {
        foreach ($point as $key => $value) {
            if ($key !== 'name' && $key !== 'dataSource' && is_array($value)) {
                $body = $value;
                break;
            }
        }
    }
    if ($body === null) {
        return null;
    }

    // Try known shapes, most specific first.
    if (isset($body['interval']['civilStartTime']['date'])) {
        return civilDateFrom($body['interval']['civilStartTime']['date']);
    }
    if (isset($body['sampleTime']['civilTime']['date'])) {
        return civilDateFrom($body['sampleTime']['civilTime']['date']);
    }
    if (isset($body['date'])) {
        return civilDateFrom($body['date']);
    }
    if (isset($body['interval']['startTime'])) {
        return new DateTimeImmutable(substr($body['interval']['startTime'], 0, 10), new DateTimeZone('UTC'));
    }
    if (isset($body['sampleTime']['physicalTime'])) {
        return new DateTimeImmutable(substr($body['sampleTime']['physicalTime'], 0, 10), new DateTimeZone('UTC'));
    }
    return null;
}

function lcfirstCamel(string $dashed): string
{
    $parts = explode('-', $dashed);
    $first = array_shift($parts);
    foreach ($parts as $p) {
        $first .= ucfirst($p);
    }
    return $first;
}

$dataTypes = [
    'nutrition-log', 'steps', 'heart-rate', 'heart-rate-variability',
    'daily-resting-heart-rate', 'sleep', 'weight', 'height', 'exercise',
];

$outDir = dirname($outputPath);
if (!is_dir($outDir)) {
    mkdir($outDir, 0777, true);
}
$baseName = preg_replace('/\.json$/', '', $outputPath);

$summary = [];

foreach ($dataTypes as $dataType) {
    $collected = [];
    $pageToken = null;
    $maxPages = 500;

    for ($page = 0; $page < $maxPages; $page++) {
        $result = fetchPage($accessToken, $dataType, $pageToken);
        $points = $result['dataPoints'] ?? [];
        if (empty($points)) {
            break;
        }

        $reachedCutoff = false;
        foreach ($points as $point) {
            $date = pointDate($dataType, $point);
            if ($date !== null && $date < $cutoff) {
                $reachedCutoff = true;
                continue;
            }
            $collected[] = $point;
        }

        $pageToken = $result['nextPageToken'] ?? null;
        if ($reachedCutoff || $pageToken === null || $pageToken === '') {
            break;
        }
    }

    $summary[$dataType] = count($collected);
    $perTypePath = $baseName . '-' . $dataType . '.json';
    file_put_contents($perTypePath, json_encode($collected, JSON_UNESCAPED_SLASHES));
    unset($collected);
    fwrite(STDOUT, str_pad($dataType, 26) . $summary[$dataType] . " point(s) in last {$days} days -> {$perTypePath}\n");
}

file_put_contents($baseName . '-summary.json', json_encode($summary, JSON_PRETTY_PRINT));
fwrite(STDOUT, "\nPer-type files written alongside: {$baseName}-<type>.json\n");
fwrite(STDOUT, "Cutoff date (UTC): " . $cutoff->format('Y-m-d') . "\n");

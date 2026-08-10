<?php

declare(strict_types=1);

/**
 * Exploratory CLI script: dumps nutrition-log data points for the last N
 * days (default 10) so we can see the real API response shape before
 * designing the MySQL schema. Not part of the app's request flow.
 *
 * The API's `filter` query param isn't accepted for nutritionLog (only
 * some data types support server-side interval filtering), so this
 * paginates the unfiltered list (newest first) and stops once entries
 * fall outside the requested window, filtering client-side.
 *
 * Usage: php scripts/fetch-nutrition-test.php [days]
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
$cutoff = (new DateTimeImmutable('today', new DateTimeZone('UTC')))->modify("-{$days} days");

function fetchPage(string $accessToken, ?string $pageToken): array
{
    $params = ['pageSize' => 500];
    if ($pageToken !== null) {
        $params['pageToken'] = $pageToken;
    }

    $url = 'https://health.googleapis.com/v4/users/me/dataTypes/nutrition-log/dataPoints?' . http_build_query($params);

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
    if ($body === false) {
        fwrite(STDERR, 'cURL error: ' . curl_error($ch) . "\n");
        exit(1);
    }
    $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($status !== 200) {
        fwrite(STDERR, "HTTP {$status}: {$body}\n");
        exit(1);
    }

    return json_decode($body, true);
}

function civilDate(array $dataPoint): ?DateTimeImmutable
{
    $date = $dataPoint['nutritionLog']['interval']['civilStartTime']['date'] ?? null;
    if ($date === null) {
        return null;
    }
    return new DateTimeImmutable(sprintf('%04d-%02d-%02d', $date['year'], $date['month'], $date['day']));
}

$collected = [];
$pageToken = null;
$maxPages = 30;

for ($page = 0; $page < $maxPages; $page++) {
    $result = fetchPage($accessToken, $pageToken);
    $points = $result['dataPoints'] ?? [];

    $reachedCutoff = false;
    foreach ($points as $point) {
        $date = civilDate($point);
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

$debugPath = __DIR__ . '/../storage/debug-nutrition-last' . $days . 'days.json';
file_put_contents($debugPath, json_encode($collected, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));

// Summary
$byDate = [];
$nutrientTypesSeen = [];
foreach ($collected as $point) {
    $date = civilDate($point)?->format('Y-m-d') ?? 'unknown';
    $byDate[$date] = ($byDate[$date] ?? 0) + 1;
    foreach ($point['nutritionLog']['nutrients'] ?? [] as $n) {
        if (isset($n['nutrient'])) {
            $nutrientTypesSeen[$n['nutrient']] = true;
        }
    }
}
krsort($byDate);

fwrite(STDOUT, "Entries in last {$days} days: " . count($collected) . "\n");
fwrite(STDOUT, "Full data written to: {$debugPath}\n\n");
fwrite(STDOUT, "By date:\n");
foreach ($byDate as $date => $count) {
    fwrite(STDOUT, "  {$date}: {$count}\n");
}
fwrite(STDOUT, "\nDistinct nutrient types seen: " . implode(', ', array_keys($nutrientTypesSeen)) . "\n");

if (!empty($collected)) {
    fwrite(STDOUT, "\nSample entry:\n");
    fwrite(STDOUT, json_encode($collected[0], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n");
}

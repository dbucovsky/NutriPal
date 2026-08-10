<?php

declare(strict_types=1);

require_once __DIR__ . '/bootstrap.php';

if (isset($_GET['error'])) {
    http_response_code(400);
    echo 'Google returned an error: ' . htmlspecialchars($_GET['error'], ENT_QUOTES);
    exit;
}

$state = $_GET['state'] ?? '';
$expectedState = $_SESSION['oauth_state'] ?? null;
unset($_SESSION['oauth_state']);

if ($expectedState === null || !hash_equals($expectedState, $state)) {
    http_response_code(400);
    echo 'Invalid or expired OAuth state.';
    exit;
}

$code = $_GET['code'] ?? '';
if ($code === '') {
    http_response_code(400);
    echo 'Missing authorization code.';
    exit;
}

try {
    $tokens = makeGoogleOAuth()->exchangeCodeForToken($code);
} catch (Throwable $e) {
    http_response_code(502);
    echo 'Token exchange failed: ' . htmlspecialchars($e->getMessage(), ENT_QUOTES);
    exit;
}

makeTokenStore()->save($tokens);

echo 'Connected to Google Health. You can close this tab.';

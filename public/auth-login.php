<?php

declare(strict_types=1);

require_once __DIR__ . '/bootstrap.php';

$state = bin2hex(random_bytes(16));
$_SESSION['oauth_state'] = $state;

$authUrl = makeGoogleOAuth()->buildAuthUrl($state);

header('Location: ' . $authUrl);
exit;

<?php

declare(strict_types=1);

require_once __DIR__ . '/bootstrap.php';

$tokens = makeTokenStore()->load();
$connected = $tokens !== null && isset($tokens['refresh_token']);

?><!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>NutriPal</title></head>
<body>
<h1>NutriPal</h1>
<?php if ($connected): ?>
    <p>Connected to Google Health.</p>
<?php else: ?>
    <p>Not connected to Google Health yet.</p>
    <p><a href="/auth-login.php">Connect Google Health</a></p>
<?php endif; ?>
</body>
</html>

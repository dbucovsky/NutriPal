<?php

declare(strict_types=1);

// Placeholder login: no password, no hashing, no session/cookie, no
// authorization of any kind. Exists purely to give the frontend a real
// "current user" concept (instead of a hardcoded id) and to exercise a
// POST round-trip before more screens get built. A real auth system is
// future work — see doc/wiki/Architecture.md.
//
// POST { "email": "..." } -> 200 {id, email, name} | 404 {error}

require_once __DIR__ . '/../../src/Env.php';
require_once __DIR__ . '/../../src/Database.php';

Env::load(__DIR__ . '/../../.env');
header('Content-Type: application/json');

$body = json_decode(file_get_contents('php://input') ?: '', true);
$email = is_array($body) ? trim((string) ($body['email'] ?? '')) : '';

if ($email === '') {
    http_response_code(400);
    echo json_encode(['error' => 'email is required']);
    exit;
}

$pdo = Database::connect();
$stmt = $pdo->prepare('SELECT id, email, name FROM users WHERE email = ? AND status_id = 2');
$stmt->execute([$email]);
$user = $stmt->fetch(PDO::FETCH_ASSOC);

if ($user === false) {
    http_response_code(404);
    echo json_encode(['error' => 'no user with that email']);
    exit;
}

echo json_encode($user);

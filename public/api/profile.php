<?php

declare(strict_types=1);

// GET  /api/profile.php?user_id=2
//      -> 200 {birth_date, gender_id, max_hr_source, max_hr_age_estimate,
//              max_hr_observed_estimate, max_hr_manual_override,
//              max_heart_rate, max_heart_rate_source}
//      (the last two are the resolved "effective" value/source; the rest
//      are per-source detail for the Settings panel, which shows all three)
// POST /api/profile.php
//      { "user_id": 2, "birth_date"?: "YYYY-MM-DD", "gender_id"?: 1,
//        "max_heart_rate_override"?: 190, "max_hr_source"?: "age"|"observed"|"manual" }
//      -> 200 same shape as GET
// birth_date/gender_id/max_hr_source are only written when present in the
// body, so a request can update just one field.

require_once __DIR__ . '/../../src/Env.php';
require_once __DIR__ . '/../../src/Database.php';
require_once __DIR__ . '/../../src/MaxHeartRate.php';

Env::load(__DIR__ . '/../../.env');
header('Content-Type: application/json');

$method = $_SERVER['REQUEST_METHOD'];
$userId = $method === 'GET'
    ? (isset($_GET['user_id']) ? (int) $_GET['user_id'] : 0)
    : (int) (json_decode(file_get_contents('php://input') ?: '', true)['user_id'] ?? 0);

if ($userId <= 0) {
    http_response_code(400);
    echo json_encode(['error' => 'user_id is required']);
    exit;
}

$pdo = Database::connect();

if ($method === 'POST') {
    $body = json_decode(file_get_contents('php://input') ?: '', true);
    $body = is_array($body) ? $body : [];

    if (array_key_exists('birth_date', $body) && $body['birth_date'] !== null) {
        $birthDate = DateTimeImmutable::createFromFormat('Y-m-d', (string) $body['birth_date']);
        $today = new DateTimeImmutable('today');
        if ($birthDate === false || $birthDate > $today || $birthDate < $today->modify('-130 years')) {
            http_response_code(400);
            echo json_encode(['error' => 'birth_date must be a real date, not in the future']);
            exit;
        }
    }

    if (array_key_exists('birth_date', $body) || array_key_exists('gender_id', $body)) {
        $fields = [];
        $params = [];
        if (array_key_exists('birth_date', $body)) {
            $fields[] = 'birth_date = ?';
            $params[] = $body['birth_date'] !== null ? (string) $body['birth_date'] : null;
        }
        if (array_key_exists('gender_id', $body)) {
            $fields[] = 'gender_id = ?';
            $params[] = $body['gender_id'] !== null ? (int) $body['gender_id'] : null;
        }
        $params[] = $userId;
        $pdo->prepare('UPDATE users SET ' . implode(', ', $fields) . ' WHERE id = ?')->execute($params);
    }

    if (isset($body['max_heart_rate_override'])) {
        MaxHeartRate::setManualOverride($pdo, $userId, (int) $body['max_heart_rate_override']);
    }

    if (isset($body['max_hr_source']) && in_array($body['max_hr_source'], ['age', 'observed', 'manual'], true)) {
        MaxHeartRate::setSource($pdo, $userId, $body['max_hr_source']);
    }
}

$userStmt = $pdo->prepare('SELECT birth_date, gender_id FROM users WHERE id = ?');
$userStmt->execute([$userId]);
$user = $userStmt->fetch(PDO::FETCH_ASSOC);

if ($user === false) {
    http_response_code(404);
    echo json_encode(['error' => 'no such user']);
    exit;
}

$maxHr = MaxHeartRate::getAllEstimates($pdo, $userId);

echo json_encode([
    'birth_date' => $user['birth_date'],
    'gender_id' => $user['gender_id'] !== null ? (int) $user['gender_id'] : null,
    'max_hr_source' => $maxHr['source'],
    'max_hr_age_estimate' => $maxHr['age'],
    'max_hr_observed_estimate' => $maxHr['observed'],
    'max_hr_manual_override' => $maxHr['manual'],
    'max_heart_rate' => $maxHr['effective'],
    'max_heart_rate_source' => $maxHr['effective_source'],
]);

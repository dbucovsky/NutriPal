<?php

declare(strict_types=1);

// GET /api/faq.php -> [{id, question, answer}, ...] ordered for display.
// question/answer are Markdown, rendered client-side (see frontend/faq.html).
// Not user-specific - no user_id needed.

require_once __DIR__ . '/../../src/Env.php';
require_once __DIR__ . '/../../src/Database.php';

Env::load(__DIR__ . '/../../.env');
header('Content-Type: application/json');

$pdo = Database::connect();
$stmt = $pdo->query(
    'SELECT id, question, answer FROM faq_entries WHERE is_obsolete = FALSE ORDER BY display_order, id'
);

$entries = array_map(
    fn (array $row): array => [
        'id' => (int) $row['id'],
        'question' => $row['question'],
        'answer' => $row['answer'],
    ],
    $stmt->fetchAll(PDO::FETCH_ASSOC)
);

echo json_encode($entries);

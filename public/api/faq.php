<?php

declare(strict_types=1);

// GET /api/faq.php -> [{id, section_id, section, question, answer}, ...]
// ordered by section (lut_faq_section's seeded id order - General first,
// then one section per tab, then Settings, then Contact & Support last),
// then display_order within a section. question/answer are Markdown,
// rendered client-side (see frontend/faq.html). Not user-specific - no
// user_id needed.

require_once __DIR__ . '/../../src/Env.php';
require_once __DIR__ . '/../../src/Database.php';

Env::load(__DIR__ . '/../../.env');
header('Content-Type: application/json');

$pdo = Database::connect();
$stmt = $pdo->query(
    'SELECT fe.id, fe.section_id, ls.name AS section_name, fe.question, fe.answer
     FROM faq_entries fe
     JOIN lut_faq_section ls ON ls.id = fe.section_id
     WHERE fe.is_obsolete = FALSE
     ORDER BY fe.section_id, fe.display_order, fe.id'
);

$entries = array_map(
    fn (array $row): array => [
        'id' => (int) $row['id'],
        'section_id' => (int) $row['section_id'],
        'section' => $row['section_name'],
        'question' => $row['question'],
        'answer' => $row['answer'],
    ],
    $stmt->fetchAll(PDO::FETCH_ASSOC)
);

echo json_encode($entries);

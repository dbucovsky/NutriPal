<?php

declare(strict_types=1);

/**
 * A user's daily step target, used by the Steps tab to classify a day as
 * bad/good/great (< goal / >= goal / >= goal*2). Shared between
 * public/api/profile.php (read/write the Settings value) and
 * public/api/steps.php (apply it), so both agree on the default.
 */
final class StepsGoal
{
    public const DEFAULT_GOAL = 10000;

    /** Never null - falls back to DEFAULT_GOAL when the user hasn't set one. */
    public static function get(PDO $pdo, int $userId): int
    {
        $stmt = $pdo->prepare('SELECT steps_goal FROM users WHERE id = ?');
        $stmt->execute([$userId]);
        $goal = $stmt->fetchColumn();
        return $goal !== false && $goal !== null ? (int) $goal : self::DEFAULT_GOAL;
    }

    public static function set(PDO $pdo, int $userId, int $goal): void
    {
        $pdo->prepare('UPDATE users SET steps_goal = ? WHERE id = ?')->execute([$goal, $userId]);
    }
}

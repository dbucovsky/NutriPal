<?php

declare(strict_types=1);

/**
 * Computes the two lookback windows scripts/sync-google-health.php's
 * --quick mode uses (nutrition + weight get a longer one, everything else
 * a shorter one), and records when a live sync last completed so the next
 * quick sync knows where to start from.
 *
 * Both windows are anchored on users.last_sync_completed_at, not "now" -
 * the whole point is to sync "what's changed since we last synced", not a
 * fixed window that re-fetches the same days over and over regardless of
 * how recently the last sync ran. The one exception: the FIRST quick sync
 * after a login gets a wider 7-day margin on both windows, in case the app
 * was closed for a while and nothing kept the data current in the
 * meantime - detected by comparing the last completed sync against the
 * user's own most recent successful login_attempts row, not any separate
 * "have I already synced this session" flag, since that fact is already
 * fully derivable from the two timestamps this class exists to track.
 */
final class SyncSchedule
{
    private const FIRST_SINCE_LOGIN_DAYS = 7;
    private const FOOD_WEIGHT_DAYS = 4;
    private const OTHER_HOURS = 4;

    /**
     * @return array{food_weight: DateTimeImmutable, other: DateTimeImmutable}
     */
    public static function quickSyncCutoffs(PDO $pdo, int $userId): array
    {
        $userStmt = $pdo->prepare('SELECT last_sync_completed_at FROM users WHERE id = ?');
        $userStmt->execute([$userId]);
        $lastSyncRaw = $userStmt->fetchColumn();
        $lastSync = $lastSyncRaw !== false && $lastSyncRaw !== null
            ? new DateTimeImmutable($lastSyncRaw, new DateTimeZone('UTC'))
            : null;

        if (self::isFirstSinceLogin($pdo, $userId, $lastSync)) {
            // No prior sync at all anchors on "now" instead - reproduces
            // today's existing first-ever-sync behavior (a plain 7-day
            // incremental) rather than needing a separate bootstrap case.
            $anchor = $lastSync ?? new DateTimeImmutable('now', new DateTimeZone('UTC'));
            $cutoff = $anchor->modify('-' . self::FIRST_SINCE_LOGIN_DAYS . ' days');
            return ['food_weight' => $cutoff, 'other' => $cutoff];
        }

        return [
            'food_weight' => $lastSync->modify('-' . self::FOOD_WEIGHT_DAYS . ' days'),
            'other' => $lastSync->modify('-' . self::OTHER_HOURS . ' hours'),
        ];
    }

    private static function isFirstSinceLogin(PDO $pdo, int $userId, ?DateTimeImmutable $lastSync): bool
    {
        if ($lastSync === null) {
            return true;
        }

        $loginStmt = $pdo->prepare(
            'SELECT created_ts FROM login_attempts WHERE user_id = ? AND success = TRUE ORDER BY created_ts DESC LIMIT 1'
        );
        $loginStmt->execute([$userId]);
        $lastLoginRaw = $loginStmt->fetchColumn();
        if ($lastLoginRaw === false || $lastLoginRaw === null) {
            return false;
        }

        $lastLogin = new DateTimeImmutable($lastLoginRaw, new DateTimeZone('UTC'));
        return $lastSync < $lastLogin;
    }

    public static function recordSyncCompleted(PDO $pdo, int $userId): void
    {
        $pdo->prepare('UPDATE users SET last_sync_completed_at = ? WHERE id = ?')
            ->execute([(new DateTimeImmutable('now', new DateTimeZone('UTC')))->format('Y-m-d H:i:s'), $userId]);
    }
}

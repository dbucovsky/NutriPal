<?php

declare(strict_types=1);

/**
 * Local-day bucketing for API endpoints that take a ?date= param. Computes
 * the requested calendar day's own midnight-to-midnight window in
 * APP_TIMEZONE and converts it to UTC for querying UTC-stored DATETIME
 * columns — never a naive UTC DATE() comparison, which misattributes
 * entries near local midnight (confirmed a real issue during this
 * project's Health-Connect-vs-live-API comparison work, see
 * doc/wiki/Data-Sync.md).
 */
final class LocalDay
{
    /** @return array{0: string, 1: string, 2: string} [localDate, utcStart, utcEnd] as Y-m-d / Y-m-d H:i:s strings */
    public static function resolve(string $timezone, ?string $dateParam): array
    {
        $tz = new DateTimeZone($timezone);
        $localDay = $dateParam !== null
            ? new DateTimeImmutable($dateParam, $tz)
            : new DateTimeImmutable('today', $tz);

        $dayStart = $localDay->setTime(0, 0, 0)->setTimezone(new DateTimeZone('UTC'));
        $dayEnd = $dayStart->modify('+1 day');

        return [$localDay->format('Y-m-d'), $dayStart->format('Y-m-d H:i:s'), $dayEnd->format('Y-m-d H:i:s')];
    }
}

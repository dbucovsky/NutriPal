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

    /**
     * Same idea as resolve(), but for a whole view range instead of one day
     * - still a single midnight-aligned UTC window (start inclusive, end
     * exclusive) so range queries stay one indexed scan, not a per-day loop.
     *
     * @return array{0: string, 1: string, 2: string, 3: string} [startLocalDate, endLocalDate, utcStart, utcEnd]
     */
    public static function resolveRange(string $timezone, string $view, ?string $dateParam, ?string $endDateParam): array
    {
        $tz = new DateTimeZone($timezone);
        $anchor = $dateParam !== null
            ? new DateTimeImmutable($dateParam, $tz)
            : new DateTimeImmutable('today', $tz);

        switch ($view) {
            case 'week':
                // Sunday-Saturday, matching the frontend's WEEKDAYS order.
                $start = $anchor->modify('-' . $anchor->format('w') . ' days');
                $end = $start->modify('+6 days');
                break;
            case 'month':
                $start = $anchor->modify('first day of this month');
                $end = $anchor->modify('last day of this month');
                break;
            case 'year':
                $start = $anchor->setDate((int) $anchor->format('Y'), 1, 1);
                $end = $anchor->setDate((int) $anchor->format('Y'), 12, 31);
                break;
            case 'custom':
                if ($endDateParam === null) {
                    throw new InvalidArgumentException('end_date is required for a custom view');
                }
                $start = $anchor;
                $end = new DateTimeImmutable($endDateParam, $tz);
                break;
            case 'day':
                $start = $anchor;
                $end = $anchor;
                break;
            default:
                throw new InvalidArgumentException("unknown view: {$view}");
        }

        $utcStart = $start->setTime(0, 0, 0)->setTimezone(new DateTimeZone('UTC'));
        $utcEnd = $end->setTime(0, 0, 0)->setTimezone(new DateTimeZone('UTC'))->modify('+1 day');

        return [$start->format('Y-m-d'), $end->format('Y-m-d'), $utcStart->format('Y-m-d H:i:s'), $utcEnd->format('Y-m-d H:i:s')];
    }

    /** Converts a UTC "Y-m-d H:i:s" column value back to its local calendar date, for grouping range-query rows by day. */
    public static function toLocalDate(string $timezone, string $utcDateTimeStr): string
    {
        $utc = new DateTimeImmutable($utcDateTimeStr, new DateTimeZone('UTC'));
        return $utc->setTimezone(new DateTimeZone($timezone))->format('Y-m-d');
    }
}

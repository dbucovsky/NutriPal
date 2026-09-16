<?php

declare(strict_types=1);

/**
 * Thrown when Google rejects a refresh_token with "invalid_grant" - the
 * stored token is expired or revoked, not a transient/network failure.
 * While the OAuth consent screen is in Testing status, Google auto-expires
 * refresh tokens after ~7 days, so this is expected to happen periodically
 * until the app is moved to production.
 */
final class GoogleAuthExpiredException extends RuntimeException
{
}

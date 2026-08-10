<?php

declare(strict_types=1);

/**
 * Temporary token storage until the MySQL schema is designed — swap this
 * out for a database-backed store once that's reviewed.
 */
final class TokenStore
{
    public function __construct(private string $path)
    {
    }

    public function save(array $tokenResponse): void
    {
        $existing = $this->load() ?? [];

        // A refresh_token is only sent on first consent; preserve it if this
        // save came from a refresh_token grant response that omits it.
        $merged = array_merge($existing, $tokenResponse);
        $merged['obtained_at'] = time();

        file_put_contents($this->path, json_encode($merged, JSON_PRETTY_PRINT));
        @chmod($this->path, 0600);
    }

    public function load(): ?array
    {
        if (!is_file($this->path)) {
            return null;
        }

        $data = json_decode((string) file_get_contents($this->path), true);
        return is_array($data) ? $data : null;
    }
}

<?php

declare(strict_types=1);

final class GoogleOAuth
{
    private const AUTH_URI = 'https://accounts.google.com/o/oauth2/v2/auth';
    private const TOKEN_URI = 'https://oauth2.googleapis.com/token';

    public function __construct(
        private string $clientId,
        private string $clientSecret,
        private string $redirectUri,
        private string $scope = 'https://www.googleapis.com/auth/googlehealth.nutrition.readonly '
            . 'https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly '
            . 'https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly '
            . 'https://www.googleapis.com/auth/googlehealth.sleep.readonly'
    ) {
    }

    public function buildAuthUrl(string $state): string
    {
        $params = [
            'client_id' => $this->clientId,
            'redirect_uri' => $this->redirectUri,
            'response_type' => 'code',
            'access_type' => 'offline',
            'scope' => $this->scope,
            'prompt' => 'consent',
            'state' => $state,
        ];

        return self::AUTH_URI . '?' . http_build_query($params);
    }

    /** @return array{access_token:string,refresh_token?:string,expires_in:int,scope:string,token_type:string} */
    public function exchangeCodeForToken(string $code): array
    {
        return $this->postToken([
            'client_id' => $this->clientId,
            'client_secret' => $this->clientSecret,
            'code' => $code,
            'grant_type' => 'authorization_code',
            'redirect_uri' => $this->redirectUri,
        ]);
    }

    /** @return array{access_token:string,expires_in:int,scope:string,token_type:string} */
    public function refreshAccessToken(string $refreshToken): array
    {
        return $this->postToken([
            'client_id' => $this->clientId,
            'client_secret' => $this->clientSecret,
            'refresh_token' => $refreshToken,
            'grant_type' => 'refresh_token',
        ]);
    }

    /** @param array<string,string> $params */
    private function postToken(array $params): array
    {
        $ch = curl_init(self::TOKEN_URI);
        curl_setopt_array($ch, [
            CURLOPT_POST => true,
            CURLOPT_POSTFIELDS => http_build_query($params),
            CURLOPT_HTTPHEADER => ['Content-Type: application/x-www-form-urlencoded'],
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => 15,
        ]);

        $body = curl_exec($ch);
        if ($body === false) {
            $error = curl_error($ch);
            curl_close($ch);
            throw new RuntimeException("Google token request failed: {$error}");
        }

        $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        $data = json_decode($body, true);
        if ($status !== 200 || !is_array($data)) {
            $message = is_array($data) ? ($data['error_description'] ?? $data['error'] ?? $body) : $body;
            throw new RuntimeException("Google token request returned HTTP {$status}: {$message}");
        }

        return $data;
    }
}

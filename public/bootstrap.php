<?php

declare(strict_types=1);

require_once __DIR__ . '/../src/Env.php';
require_once __DIR__ . '/../src/GoogleOAuth.php';
require_once __DIR__ . '/../src/TokenStore.php';

Env::load(__DIR__ . '/../.env');

session_start();

function makeGoogleOAuth(): GoogleOAuth
{
    return new GoogleOAuth(
        clientId: Env::require('GOOGLE_CLIENT_ID'),
        clientSecret: Env::require('GOOGLE_CLIENT_SECRET'),
        redirectUri: Env::require('GOOGLE_REDIRECT_URI'),
    );
}

function makeTokenStore(): TokenStore
{
    return new TokenStore(__DIR__ . '/../storage/google-tokens.json');
}

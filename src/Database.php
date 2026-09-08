<?php

declare(strict_types=1);

final class Database
{
    private static ?PDO $connection = null;

    public static function connect(): PDO
    {
        if (self::$connection !== null) {
            return self::$connection;
        }

        $host = Env::get('DB_HOST', 'localhost');
        $name = Env::require('DB_NAME');
        $user = Env::get('DB_USER', 'root');
        $pass = Env::get('DB_PASS', '');

        $pdo = new PDO(
            "mysql:host={$host};dbname={$name};charset=utf8mb4",
            $user,
            $pass,
            [
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_EMULATE_PREPARES => false,
            ]
        );

        self::$connection = $pdo;
        return $pdo;
    }
}

"""
Хранилище публичных ключей разработчиков
"""

DEVELOPER_KEYS = {
    "Lev Petunin <lm.petunin@sign-sql.ru>": """
-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE/WwJK1Wx56u6qQUg0hmTPart8RPd
Sttp4apbgiu7HansWHURD1QjDPJJnOcgHvOUnkgNcZWs3Atf6RvjefSXvw==
-----END PUBLIC KEY-----
    """,
    "Ivan Ivanov <ivan@example.com>": """
-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE...
-----END PUBLIC KEY-----
    """,
}

# Кэш проверенных миграций
verified_migrations_cache = set()
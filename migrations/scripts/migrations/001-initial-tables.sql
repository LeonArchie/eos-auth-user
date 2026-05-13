-- SIGNATURE: MEUCIQCjxMs7KOMNLHts10Ct5nUMT0MV31NORpopdFkwq01cEwIgBq1Q/on2AePgwuFVNRHQNxHSsVjjH87EfmGlEA8J6SA=
-- SIGNED_BY: Lev Petunin <lm.petunin@sign-sql.ru>
-- SIGNED_AT: 2026-03-03T18:16:44Z
-- CHECKSUM: 3042ecdc6e601f33b55b4bf0845672920d45ccfa660ac0fa75fd91da41533c3c
-- SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
-- Copyright (C) 2025 Петунин Лев Михайлович

-- Создание таблицы пользователей
CREATE TABLE users (
    user_id UUID PRIMARY KEY,
    userlogin VARCHAR(20) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER 
ON TABLE users TO "db_admin";
GRANT ALL PRIVILEGES ON users TO "db_admin";


-- Комментарии к таблице users
COMMENT ON TABLE users IS 'Основная таблица для хранения информации о пользователях системы';
COMMENT ON COLUMN users.user_id IS 'Уникальный идентификатор пользователя в формате UUID';
COMMENT ON COLUMN users.userlogin IS 'Уникальный логин пользователя (максимальная длина 20 символов)';
COMMENT ON COLUMN users.password_hash IS 'Хэш пароля пользователя, созданный алгоритмом Argon2id (переменная длина, до 255 символов)';
COMMENT ON COLUMN users.active IS 'Флаг активности учетной записи (true - активна, false - деактивирована/заблокирована)';
COMMENT ON COLUMN users.created_at IS 'Дата и время создания учетной записи пользователя (часовой пояс UTC)';
COMMENT ON COLUMN users.updated_at IS 'Дата и время последнего обновления информации о пользователе (часовой пояс UTC)';


-- Создание таблицы сессий
CREATE TABLE sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    access_token TEXT NOT NULL,
    refresh_token_hash VARCHAR(255) NOT NULL,
    user_agent VARCHAR(200),
    ip_address VARCHAR(45),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    last_used_at TIMESTAMP WITH TIME ZONE
);

GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER 
ON TABLE sessions TO "db_admin";
GRANT ALL PRIVILEGES ON sessions TO "db_admin";


-- Комментарии к таблице sessions
COMMENT ON TABLE sessions IS 'Таблица для хранения активных сессий пользователей';
COMMENT ON COLUMN sessions.session_id IS 'Уникальный идентификатор сессии в формате UUID (генерируется автоматически)';
COMMENT ON COLUMN sessions.user_id IS 'Ссылка на пользователя в таблице users (каскадное удаление при удалении пользователя)';
COMMENT ON COLUMN sessions.access_token IS 'JWT токен доступа';
COMMENT ON COLUMN sessions.refresh_token_hash IS 'Хэш токена обновления (Argon2id, переменная длина, до 255 символов)';
COMMENT ON COLUMN sessions.user_agent IS 'Информация о браузере/устройстве пользователя (максимальная длина 200 символов)';
COMMENT ON COLUMN sessions.ip_address IS 'IP-адрес пользователя (поддерживает IPv6, максимальная длина 45 символов)';
COMMENT ON COLUMN sessions.created_at IS 'Дата и время создания сессии (часовой пояс UTC)';
COMMENT ON COLUMN sessions.expires_at IS 'Дата и время истечения срока действия сессии (часовой пояс UTC)';
COMMENT ON COLUMN sessions.is_revoked IS 'Флаг отзыва сессии (true - отозвана, false - активна)';
COMMENT ON COLUMN sessions.last_used_at IS 'Дата и время последнего использования сессии (часовой пояс UTC)';

-- Создание индексов
CREATE INDEX idx_users_login ON users(userlogin);
CREATE INDEX idx_users_active ON users(active) WHERE active = true;
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_access_token ON sessions(access_token);
CREATE INDEX idx_sessions_expires ON sessions(expires_at) WHERE NOT is_revoked;
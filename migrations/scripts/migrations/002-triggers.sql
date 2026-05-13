-- SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
-- Copyright (C) 2025 Петунин Лев Михайлович

-- Триггер для обновления временных меток пользователей
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_timestamp
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- Триггер для проверки времени жизни сессии
CREATE OR REPLACE FUNCTION validate_session_expiration()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.expires_at <= NEW.created_at THEN
        RAISE EXCEPTION 'Время истечения сессии должно быть позже времени создания';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_session_expiration
BEFORE INSERT OR UPDATE ON sessions
FOR EACH ROW EXECUTE FUNCTION validate_session_expiration();

-- Триггер для автоматической очистки старых сессий
CREATE OR REPLACE FUNCTION cleanup_old_sessions()
RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM sessions 
    WHERE user_id = NEW.user_id 
    AND expires_at <= NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_cleanup_old_sessions
BEFORE INSERT ON sessions
FOR EACH ROW EXECUTE FUNCTION cleanup_old_sessions();

-- Комментарии
COMMENT ON FUNCTION update_timestamp() IS 'Функция для обновления временных меток пользователей';
COMMENT ON FUNCTION validate_session_expiration() IS 'Проверка корректности времени жизни сессии';
COMMENT ON FUNCTION cleanup_old_sessions() IS 'Автоматическая очистка просроченных сессий';
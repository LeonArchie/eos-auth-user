-- ROLLBACK for 001-initial-tables.sql
-- Откатывает создание таблиц users и sessions

-- Удаляем индексы (важно сделать до удаления таблиц)
DROP INDEX IF EXISTS idx_sessions_expires;
DROP INDEX IF EXISTS idx_sessions_access_token;
DROP INDEX IF EXISTS idx_sessions_user_id;
DROP INDEX IF EXISTS idx_users_active;
DROP INDEX IF EXISTS idx_users_login;

-- Удаляем таблицы в правильном порядке (учитывая внешние ключи)
DROP TABLE IF EXISTS sessions CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Подтверждение отката
DO $$
BEGIN
    RAISE NOTICE 'Rollback 001 completed: Tables users and sessions dropped';
END $$;
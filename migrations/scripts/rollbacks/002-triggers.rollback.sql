-- SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
-- Copyright (C) 2025 Петунин Лев Михайлович

-- ROLLBACK for 002-triggers.sql
-- Удаляет триггеры и функции

-- Удаляем триггеры
DROP TRIGGER IF EXISTS trg_cleanup_old_sessions ON sessions;
DROP TRIGGER IF EXISTS trg_check_session_expiration ON sessions;
DROP TRIGGER IF EXISTS update_users_timestamp ON users;

-- Удаляем функции
DROP FUNCTION IF EXISTS cleanup_old_sessions();
DROP FUNCTION IF EXISTS validate_session_expiration();
DROP FUNCTION IF EXISTS update_timestamp();

-- Подтверждение
DO $$
BEGIN
    RAISE NOTICE 'Rollback 002 completed: Triggers and functions dropped';
END $$;
-- SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
-- Copyright (C) 2025 Петунин Лев Михайлович

-- ROLLBACK for 003-all-privileges.sql
-- Откатывает назначение прав (требует осторожности)

-- Удаляем созданные индексы
DROP INDEX IF EXISTS idx_applied_migrations_name_app;
DROP INDEX IF EXISTS idx_applied_migrations_applied_at;

-- Удаляем функцию назначения прав
DROP FUNCTION IF EXISTS grant_applied_migrations_to_user(TEXT);

-- Отзываем права у всех пользователей (кроме администратора)
DO $$
DECLARE
    user_record RECORD;
BEGIN
    FOR user_record IN 
        SELECT rolname 
        FROM pg_roles 
        WHERE rolcanlogin = true 
        AND rolname NOT LIKE 'pg_%'
        AND rolname != 'postgres'
        AND rolname != 'db_admin'
    LOOP
        BEGIN
            EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE applied_migrations FROM %I;', user_record.rolname);
            RAISE NOTICE 'Revoked privileges for: %', user_record.rolname;
        EXCEPTION
            WHEN OTHERS THEN
                RAISE NOTICE 'Could not revoke from %: %', user_record.rolname, SQLERRM;
        END;
    END LOOP;
END $$;

RAISE NOTICE 'Rollback 003: Privileges revoked, but applied_migrations table still exists';
RAISE NOTICE 'Warning: applied_migrations is managed by Liquibase itself';
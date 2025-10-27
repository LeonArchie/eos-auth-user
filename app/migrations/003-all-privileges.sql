-- SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
-- Copyright (C) 2025 Петунин Лев Михайлович

-- Миграция 003: Настройка прав доступа к таблице applied_migrations для всех пользователей

-- Назначаем права всем существующим пользователям
DO $$
DECLARE
    user_record RECORD;
    users_count INTEGER := 0;
BEGIN
    -- Получаем всех пользователей (роли с правом логина)
    FOR user_record IN 
        SELECT rolname 
        FROM pg_roles 
        WHERE rolcanlogin = true 
        AND rolname NOT LIKE 'pg_%'
        AND rolname != 'postgres'
        AND rolname != 'gen_user'
    LOOP
        BEGIN
            -- Назначаем права каждому существующему пользователю
            EXECUTE format('
                GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER 
                ON TABLE applied_migrations TO %I;
            ', user_record.rolname);
            
            users_count := users_count + 1;
            RAISE NOTICE 'Назначены права на applied_migrations для пользователя: %', user_record.rolname;
        EXCEPTION
            WHEN OTHERS THEN
                RAISE NOTICE 'Не удалось назначить права для пользователя %: %', user_record.rolname, SQLERRM;
        END;
    END LOOP;
    
    RAISE NOTICE 'Права назначены для % пользователей', users_count;
END $$;

-- Создаем функцию для ручного назначения прав новым пользователям
CREATE OR REPLACE FUNCTION grant_applied_migrations_to_user(username TEXT)
RETURNS VOID AS $$
BEGIN
    EXECUTE format('
        GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER 
        ON TABLE applied_migrations TO %I;
    ', username);
    
    RAISE NOTICE 'Права на applied_migrations назначены пользователю: %', username;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Ошибка назначения прав для пользователя %: %', username, SQLERRM;
END;
$$ LANGUAGE plpgsql;

-- Предоставляем права на последовательность (если она существует)
DO $$
DECLARE
    user_name TEXT;
    user_names TEXT[];
BEGIN
    -- Получаем список пользователей
    SELECT ARRAY(
        SELECT rolname 
        FROM pg_roles 
        WHERE rolcanlogin = true 
        AND rolname NOT LIKE 'pg_%'
        AND rolname != 'postgres'
        AND rolname != 'DB_ADMIN'
    ) INTO user_names;
    
    -- Предоставляем права на последовательность для всех пользователей
    FOREACH user_name IN ARRAY user_names
    LOOP
        BEGIN
            EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE applied_migrations_id_seq TO %I;', user_name);
            RAISE NOTICE 'Права на последовательность назначены пользователю: %', user_name;
        EXCEPTION
            WHEN OTHERS THEN
                RAISE NOTICE 'Не удалось назначить права на последовательность для %: %', user_name, SQLERRM;
        END;
    END LOOP;
EXCEPTION
    WHEN undefined_table OR undefined_object THEN
        RAISE NOTICE 'Последовательность applied_migrations_id_seq не существует, пропускаем назначение прав';
    WHEN OTHERS THEN
        RAISE NOTICE 'Ошибка при назначении прав на последовательность: %', SQLERRM;
END $$;

-- Создаем индекс для улучшения производительности
CREATE INDEX IF NOT EXISTS idx_applied_migrations_name_app 
ON applied_migrations(name_app);

CREATE INDEX IF NOT EXISTS idx_applied_migrations_applied_at 
ON applied_migrations(applied_at);

-- Комментарии
COMMENT ON FUNCTION grant_applied_migrations_to_user(TEXT) IS 
'Функция для ручного назначения прав на таблицу applied_migrations указанному пользователю';

COMMENT ON INDEX idx_applied_migrations_name_app IS 
'Индекс для оптимизации запросов по имени приложения';

COMMENT ON INDEX idx_applied_migrations_applied_at IS 
'Индекс для оптимизации запросов по дате применения миграции';

-- Логирование выполнения миграции
DO $$
BEGIN
    RAISE NOTICE 'Миграция 003 выполнена: Настроены права доступа к таблице applied_migrations';
    RAISE NOTICE 'Для новых пользователей вызывайте: SELECT grant_applied_migrations_to_user(''username'');';
END $$;
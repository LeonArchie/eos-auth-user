# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import os
import re
import hashlib
import time
import base64
from typing import Dict, List, Tuple, Optional, Callable, Any, Set
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import logging
from pathlib import Path
from functools import wraps
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend

from maintenance.flag_state import set_migration_flag, get_migration_flag, get_db_flag
from maintenance.wait_for_flag import wait_for_db_flag
from migrations.developers_keys import DEVELOPER_KEYS, verified_migrations_cache

logger = logging.getLogger(__name__)

# Глобальная переменная для отслеживания статуса миграций
migration_complete = False

# Глобальные переменные для кэширования статуса миграций
migration_status_cache = {
    'complete': False,      # Все миграции успешно применены
    'checked': False,       # Статус был проверен
    'has_errors': False,    # Есть миграции с ошибками
    'pending_count': 0      # Количество ожидающих миграций
}

class MigrationError(Exception):
    """Класс для ошибок миграции с детальным логированием"""
    def __init__(self, message: str, migration_file: Optional[str] = None):
        self.message = message
        self.migration_file = migration_file
        logger.critical(
            f"ОШИБКА МИГРАЦИИ{' (' + migration_file + ')' if migration_file else ''}: {message}",
            exc_info=True
        )
        super().__init__(message)

class SignatureError(MigrationError):
    """Ошибка проверки подписи миграции"""
    def __init__(self, message: str, migration_file: Optional[str] = None):
        super().__init__(f"Ошибка подписи: {message}", migration_file)

# ==================== ФУНКЦИИ ДЛЯ РАБОТЫ С ПОДПИСЯМИ ====================

def extract_signature_headers(sql_content: str) -> Tuple[Dict[str, str], str]:
    """
    Извлекает заголовки подписи из SQL-скрипта.
    Возвращает (заголовки, содержимое без заголовков)
    """
    headers = {}
    lines = sql_content.splitlines()
    content_lines = []
    header_pattern = re.compile(r'^--\s*(SIGNATURE|SIGNED_BY|SIGNED_AT|CHECKSUM):\s*(.+)$')
    
    for line in lines:
        match = header_pattern.match(line)
        if match:
            key, value = match.groups()
            headers[key] = value.strip()
        else:
            content_lines.append(line)
    
    return headers, '\n'.join(content_lines)

def verify_migration_signature(migration_file: str, sql_content: str) -> bool:
    """
    Проверяет подпись SQL-скрипта миграции.
    """
    global verified_migrations_cache
    
    # Проверяем кэш
    if migration_file in verified_migrations_cache:
        logger.debug(f"Миграция {migration_file} уже проверена, используем кэш")
        return True
    
    try:
        # Извлекаем заголовки подписи
        headers, clean_content = extract_signature_headers(sql_content)
        
        # Проверяем наличие всех необходимых заголовков
        required_headers = ['SIGNATURE', 'SIGNED_BY', 'SIGNED_AT']
        missing_headers = [h for h in required_headers if h not in headers]
        
        if missing_headers:
            raise SignatureError(
                f"Отсутствуют обязательные заголовки подписи: {', '.join(missing_headers)}",
                migration_file
            )
        
        # Проверяем контрольную сумму
        if 'CHECKSUM' in headers:
            # Используем clean_content для проверки контрольной суммы
            calculated_checksum = hashlib.sha256(clean_content.encode('utf-8')).hexdigest()
            if calculated_checksum != headers['CHECKSUM']:
                raise SignatureError(
                    f"Контрольная сумма не совпадает. Ожидалось: {headers['CHECKSUM']}, "
                    f"Вычислено: {calculated_checksum}",
                    migration_file
                )
            logger.debug(f"Контрольная сумма {migration_file} совпадает")
        
        # Получаем публичный ключ разработчика
        signed_by = headers['SIGNED_BY']
        if signed_by not in DEVELOPER_KEYS:
            raise SignatureError(
                f"Разработчик '{signed_by}' не найден в хранилище ключей. "
                f"Доступные разработчики: {list(DEVELOPER_KEYS.keys())}",
                migration_file
            )
        
        # Загружаем публичный ключ
        try:
            public_key_pem = DEVELOPER_KEYS[signed_by].strip()
            public_key = load_pem_public_key(
                public_key_pem.encode('utf-8'),
                backend=default_backend()
            )
        except Exception as e:
            raise SignatureError(
                f"Ошибка загрузки публичного ключа для {signed_by}: {str(e)}",
                migration_file
            )
        
        # Проверяем тип ключа
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            raise SignatureError(
                f"Неподдерживаемый тип ключа. Ожидался ECDSA, получен {type(public_key).__name__}",
                migration_file
            )
        
        # Декодируем подпись из base64
        try:
            signature = base64.b64decode(headers['SIGNATURE'])
        except Exception as e:
            raise SignatureError(
                f"Ошибка декодирования подписи: {str(e)}",
                migration_file
            )
        
        # ИСПРАВЛЕНИЕ: Используем clean_content (без заголовков) для проверки подписи
        # так как заголовки были удалены при создании подписи
        verification_data = clean_content.encode('utf-8')
        
        # Проверяем подпись
        try:
            public_key.verify(
                signature,
                verification_data,
                ec.ECDSA(hashes.SHA256())
            )
            logger.info(f"✓ Подпись миграции {migration_file} действительна (подписано: {signed_by})")
            
            # Добавляем в кэш проверенных миграций
            verified_migrations_cache.add(migration_file)
            return True
            
        except InvalidSignature:
            raise SignatureError(
                f"Недействительная подпись для миграции {migration_file}",
                migration_file
            )
            
    except SignatureError:
        raise
    except Exception as e:
        raise SignatureError(
            f"Неожиданная ошибка при проверке подписи: {str(e)}",
            migration_file
        )

def verify_migration_file(migration_file: str, file_path: Path) -> bool:
    """
    Проверяет файл миграции на наличие действительной подписи.
    """
    global verified_migrations_cache
    
    # Проверяем кэш
    if migration_file in verified_migrations_cache:
        logger.debug(f"Миграция {migration_file} уже проверена ранее")
        return True
    
    try:
        # Читаем содержимое файла
        with open(file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # Проверяем подпись
        result = verify_migration_signature(migration_file, sql_content)
        
        # Если проверка прошла успешно, добавляем в кэш
        if result:
            verified_migrations_cache.add(migration_file)
        
        return result
        
    except SignatureError as e:
        logger.error(str(e))
        return False
    except Exception as e:
        logger.error(f"Ошибка при проверке файла миграции {migration_file}: {str(e)}")
        return False

# ==================== ДЕКОРАТОРЫ И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def with_db_session(func: Callable) -> Callable:
    """Декоратор для автоматического получения сессии БД"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        from maintenance.database_connector import get_db_connector
        connector = get_db_connector()
        with connector.get_session() as session:
            return func(session, *args, **kwargs)
    return wrapper

def _log_migration_step(step: str, details: str = "", level: str = "info") -> None:
    """Унифицированное логирование шагов миграции"""
    log_method = getattr(logger, level.lower(), logger.info)
    log_method(f"МИГРАЦИЯ: {step} {details}")

def _get_pending_migrations(applied: Dict, all_files: set) -> List[str]:
    """Получить список ожидающих миграций (не примененные или с ошибками)"""
    pending = []
    for migration_file in sorted(all_files):
        if migration_file not in applied:
            pending.append(migration_file)
        elif (migration_file in applied and 
              applied[migration_file][2] == 'error'):
            pending.append(migration_file)
    return pending

def _update_migration_cache(complete: bool, has_errors: bool, pending_count: int) -> None:
    """Обновить кэш статуса миграций"""
    global migration_status_cache
    migration_status_cache = {
        'complete': complete,
        'checked': True,
        'has_errors': has_errors,
        'pending_count': pending_count
    }

def _get_migration_status_data(session) -> Dict[str, Any]:
    """Базовая функция для получения данных о статусе миграций"""
    app_name = get_app_name()
    check_migrations_table(session)
    applied = get_applied_migrations(session, app_name)
    all_files = set(get_migration_files())
    pending = _get_pending_migrations(applied, all_files)
    has_errors = any(m[2] == 'error' for m in applied.values())
    
    return {
        'app_name': app_name,
        'applied': applied,
        'all_files': all_files,
        'pending': pending,
        'has_errors': has_errors,
        'pending_count': len(pending),
        'complete': len(pending) == 0 and not has_errors
    }

# ==================== ОСНОВНЫЕ ФУНКЦИИ ====================

def get_app_name() -> str:
    """
    Получает имя приложения из файла global.conf
    """
    try:
        current_dir = Path(__file__).parent.parent
        config_file_path = current_dir / 'global.conf'
        
        if not config_file_path.exists():
            error_msg = f"Файл конфигурации не найден: {config_file_path}"
            _log_migration_step("Ошибка", error_msg, "error")
            raise MigrationError(error_msg)

        with open(config_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('NAME_APP='):
                    app_name = line.split('=', 1)[1].strip()
                    if app_name:
                        _log_migration_step("Имя приложения получено", f"NAME_APP: {app_name}")
                        return app_name

        error_msg = "Параметр NAME_APP не найден в global.conf"
        _log_migration_step("Ошибка", error_msg, "error")
        raise MigrationError(error_msg)
        
    except Exception as e:
        error_msg = f"Ошибка чтения конфигурации: {str(e)}"
        _log_migration_step("Критическая ошибка", error_msg, "critical")
        raise MigrationError(error_msg) from e

def get_migration_files() -> List[str]:
    """
    Получаем список файлов миграций в правильном порядке
    """
    try:
        current_dir = Path(__file__).parent.parent
        migrations_dir = current_dir / 'migrations'
        
        _log_migration_step("Поиск файлов миграций", f"Директория: {migrations_dir}")
        
        if not migrations_dir.exists():
            error_msg = f"Директория с миграциями не найдена: {migrations_dir}"
            _log_migration_step("Ошибка", error_msg, "error")
            raise MigrationError(error_msg)

        files = []
        valid_files = []
        
        for f in migrations_dir.iterdir():
            if f.is_file() and f.suffix == '.sql':
                files.append(f.name)
                if re.match(r'^\d{3}-.+\.sql$', f.name):
                    valid_files.append(f.name)

        _log_migration_step(
            "Найдены файлы",
            f"Всего: {len(files)}\n"
            f"Валидных миграций: {len(valid_files)}\n"
            f"Невалидных файлов: {len(files) - len(valid_files)}"
        )

        if not valid_files:
            _log_migration_step("Нет миграций", "Валидные миграции не найдены", "warning")
            return []

        sorted_files = sorted(valid_files)
        _log_migration_step(
            "Сортировка миграций",
            f"Первая миграция: {sorted_files[0]}\n"
            f"Последняя миграция: {sorted_files[-1]}\n"
            f"Всего миграций: {len(sorted_files)}"
        )
        
        return sorted_files
        
    except Exception as e:
        error_msg = f"Ошибка чтения директории миграций: {str(e)}"
        _log_migration_step("Критическая ошибка", error_msg, "critical")
        raise MigrationError(error_msg) from e

def check_migrations_table(session) -> None:
    """
    Проверяем наличие таблицы миграций и создаем если ее нет
    """
    try:
        _log_migration_step("Проверка таблицы applied_migrations")
        
        # Проверка существования таблица
        result = session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'applied_migrations'
            )
        """))
        exists = result.scalar()
        
        if exists:
            _log_migration_step("Таблица существует", "Продолжение без создания")
            return

        _log_migration_step("Создание таблиции applied_migrations")
        
        # Создание таблицы с полем NAME_APP
        create_table_sql = """
            CREATE TABLE applied_migrations (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                name_app VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                checksum VARCHAR(64) NOT NULL,
                execution_time_ms FLOAT,
                status VARCHAR(20) NOT NULL DEFAULT 'success',
                error_message TEXT,
                signature_verified BOOLEAN DEFAULT TRUE,
                signed_by VARCHAR(255),
                signed_at TIMESTAMP WITH TIME ZONE,
                UNIQUE(name, name_app)
            )
        """
        session.execute(text(create_table_sql))
        session.commit()
        
        _log_migration_step("Таблица создана", "Успешно создана таблица applied_migrations")
        
    except SQLAlchemyError as e:
        session.rollback()
        error_msg = f"Ошибка создания таблицы миграций: {str(e)}"
        _log_migration_step("Ошибка SQL", error_msg, "error")
        raise MigrationError(error_msg) from e
    except Exception as e:
        session.rollback()
        error_msg = f"Неожиданная ошибка при работе с таблицей миграций: {str(e)}"
        _log_migration_step("Критическая ошибка", error_msg, "critical")
        raise MigrationError(error_msg) from e

def get_applied_migrations(session, app_name: str) -> Dict[str, Tuple[str, float, str]]:
    """
    Получаем список примененных миграций для конкретного приложения
    """
    try:
        _log_migration_step("Получение списка примененных миграций", f"Приложение: {app_name}")
        
        result = session.execute(text("""
            SELECT name, checksum, execution_time_ms, status
            FROM applied_migrations 
            WHERE name_app = :app_name
            ORDER BY applied_at
        """), {"app_name": app_name})
        
        migrations = {}
        for row in result.fetchall():
            migrations[row[0]] = (row[1], row[2], row[3])
        
        _log_migration_step(
            "Полученные миграции",
            f"Найдено примененных миграций: {len(migrations)}\n"
            f"Успешных: {len([m for m in migrations.values() if m[2] == 'success'])}\n"
            f"С ошибками: {len([m for m in migrations.values() if m[2] == 'error'])}"
        )
        
        return migrations
        
    except SQLAlchemyError as e:
        error_msg = f"Ошибка получения списка миграций: {str(e)}"
        _log_migration_step("Ошибка SQL", error_msg, "error")
        raise MigrationError(error_msg) from e
    except Exception as e:
        error_msg = f"Неожиданная ошибка при получении миграций: {str(e)}"
        _log_migration_step("Критическая ошибка", error_msg, "critical")
        raise MigrationError(error_msg) from e

def calculate_checksum(file_path: Path) -> str:
    """
    Вычисляем SHA-256 контрольную сумму файла миграции
    """
    try:
        _log_migration_step("Вычисление контрольной суммы", f"Файл: {file_path.name}")
        
        with open(file_path, 'rb') as f:
            content = f.read()
            checksum = hashlib.sha256(content).hexdigest()
            
        _log_migration_step(
            "Контрольная сумма вычислена",
            f"Файл: {file_path.name}\n"
            f"Размер: {len(content)} байт\n"
            f"SHA-256: {checksum}"
        )
        
        return checksum
        
    except Exception as e:
        error_msg = f"Ошибка вычисления контрольной суммы для {file_path.name}: {str(e)}"
        _log_migration_step("Ошибка", error_msg, "error")
        raise MigrationError(error_msg, file_path.name) from e

def split_sql_statements(sql: str) -> List[str]:
    """
    Разбивает SQL-скрипт на отдельные запросы с поддержкой dollar-quoted строк.
    """
    _log_migration_step("Разбор SQL на отдельные запросы")
    
    statements = []
    current = ""
    in_dollar_quote = False
    dollar_tag = ""
    
    i = 0
    n = len(sql)
    
    while i < n:
        char = sql[i]
        
        # Обработка комментариев
        if not in_dollar_quote and char == '-' and i + 1 < n and sql[i+1] == '-':
            # Пропускаем однострочный комментарий
            while i < n and sql[i] != '\n':
                i += 1
            continue
        
        # Обработка dollar-quoted строк
        if char == '$' and not in_dollar_quote:
            # Проверяем начало dollar-quoted строки
            j = i + 1
            tag = ""
            while j < n and (sql[j].isalpha() or sql[j] == '_'):
                tag += sql[j]
                j += 1
            
            if j < n and sql[j] == '$':
                in_dollar_quote = True
                dollar_tag = tag
                current += sql[i:j+1]
                i = j + 1
                continue
        
        elif char == '$' and in_dollar_quote:
            # Проверяем конец dollar-quoted строки
            j = i + 1
            tag = ""
            while j < n and (sql[j].isalpha() or sql[j] == '_'):
                tag += sql[j]
                j += 1
            
            if j < n and sql[j] == '$' and tag == dollar_tag:
                in_dollar_quote = False
                current += sql[i:j+1]
                i = j + 1
                continue
        
        # Если не в dollar-quoted строке, ищем точку с запятой
        if char == ';' and not in_dollar_quote:
            current += char
            if current.strip():
                statements.append(current.strip())
            current = ""
            i += 1
            continue
        
        current += char
        i += 1
    
    # Добавляем последний statement если он есть
    if current.strip():
        statements.append(current.strip())
    
    _log_migration_step(
        "Результат разбора SQL",
        f"Всего запросов: {len(statements)}\n"
        f"Пример запроса: {statements[0][:100] + '...' if statements else 'нет'}"
    )
    
    return statements

def apply_migration(session, migration_file: str, app_name: str) -> bool:
    """
    Применяет одну миграцию. Возвращает True если успешно, False если ошибка.
    В случае ошибки выполняется откат всех изменений этой миграции.
    Если миграция уже была применена с ошибкой, выполняется повторная попытка.
    Перед применением проверяется цифровая подпись миграции.
    """
    start_time = time.time()
    current_dir = Path(__file__).parent.parent
    file_path = current_dir / 'migrations' / migration_file
    
    # Данные для записи в БД
    signature_info = {
        'verified': False,
        'signed_by': None,
        'signed_at': None
    }
    
    try:
        _log_migration_step(
            "Начало применения миграции",
            f"Файл: {migration_file}\n"
            f"Приложение: {app_name}"
        )
        
        # Вычисление контрольной суммы файла
        file_checksum = calculate_checksum(file_path)
        
        # Чтение содержимого файла для проверки подписи
        with open(file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # Извлекаем информацию о подписи для логирования
        headers, clean_content = extract_signature_headers(sql_content)
        if 'SIGNED_BY' in headers:
            signature_info['signed_by'] = headers['SIGNED_BY']
        if 'SIGNED_AT' in headers:
            signature_info['signed_at'] = headers['SIGNED_AT']
        
        # Проверяем подпись миграции
        _log_migration_step(
            "Проверка подписи",
            f"Файл: {migration_file}\n"
            f"Подписант: {signature_info['signed_by'] or 'неизвестен'}\n"
            f"Время подписи: {signature_info['signed_at'] or 'неизвестно'}"
        )
        
        if not verify_migration_signature(migration_file, sql_content):
            error_msg = f"Недействительная подпись миграции {migration_file}"
            _log_migration_step("Ошибка подписи", error_msg, "error")
            raise SignatureError(error_msg, migration_file)
        
        signature_info['verified'] = True
        _log_migration_step("✓ Подпись действительна", f"Миграция {migration_file} прошла проверку")
        
        # Проверяем, существует ли уже запись о миграции (включая статус error)
        existing_migration = session.execute(
            text("""
                SELECT status, checksum 
                FROM applied_migrations 
                WHERE name = :name AND name_app = :name_app
            """),
            {"name": migration_file, "name_app": app_name}
        ).fetchone()
        
        # Если миграция уже существует со статусом error, выполняем UPDATE вместо INSERT
        is_retry = existing_migration and existing_migration[0] == 'error'
        
        if is_retry:
            _log_migration_step(
                "Повторное применение миграции",
                f"Миграция {migration_file} ранее завершилась ошибкой\n"
                f"Выполняется повторная попытка применения"
            )
        
        # Разбиение на отдельные запросы
        statements = split_sql_statements(clean_content)
        
        # Выполнение каждого запроса
        for i, query in enumerate(statements, 1):
            query_start = time.time()
            try:
                logger.debug(f"Выполнение запроса {i}/{len(statements)}: {query[:100]}...")
                session.execute(text(query))
                query_time = (time.time() - query_start) * 1000
                logger.debug(f"Запрос {i} выполнен за {query_time:.2f} мс")
            except Exception as e:
                logger.error(f"Ошибка в запросе {i}:\n{query[:500]}...")
                logger.error(f"Полная ошибка: {str(e)}")
                # При ошибке откатываем всю транзакцию
                session.rollback()
                raise
        
        # Фиксация миграции в БД
        execution_time = (time.time() - start_time) * 1000
        
        if is_retry:
            # Обновляем существующую запись с информацией о подписи
            session.execute(
                text("""
                    UPDATE applied_migrations 
                    SET checksum = :checksum, 
                        execution_time_ms = :execution_time,
                        status = 'success',
                        error_message = NULL,
                        signature_verified = :signature_verified,
                        signed_by = :signed_by,
                        signed_at = :signed_at::timestamp with time zone,
                        applied_at = NOW()
                    WHERE name = :name AND name_app = :name_app
                """),
                {
                    "name": migration_file, 
                    "name_app": app_name,
                    "checksum": file_checksum,
                    "execution_time": execution_time,
                    "signature_verified": signature_info['verified'],
                    "signed_by": signature_info['signed_by'],
                    "signed_at": signature_info['signed_at']
                }
            )
            _log_migration_step(
                "Миграция успешно переприменена",
                f"Файл: {migration_file}\n"
                f"Приложение: {app_name}\n"
                f"Статус изменен с 'error' на 'success'\n"
                f"Подпись проверена: {signature_info['verified']}\n"
                f"Подписант: {signature_info['signed_by']}\n"
                f"Контрольная сумма: {file_checksum}\n"
                f"Время выполнения: {execution_time:.2f} мс\n"
                f"Выполнено запросов: {len(statements)}"
            )
        else:
            # Создаем новую запись с информацией о подписи
            session.execute(
                text("""
                    INSERT INTO applied_migrations 
                    (name, name_app, checksum, execution_time_ms, status, 
                     signature_verified, signed_by, signed_at) 
                    VALUES (:name, :name_app, :checksum, :execution_time, 'success',
                            :signature_verified, :signed_by, :signed_at::timestamp with time zone)
                """),
                {
                    "name": migration_file, 
                    "name_app": app_name,
                    "checksum": file_checksum,
                    "execution_time": execution_time,
                    "signature_verified": signature_info['verified'],
                    "signed_by": signature_info['signed_by'],
                    "signed_at": signature_info['signed_at']
                }
            )
            _log_migration_step(
                "Миграция успешно применена",
                f"Файл: {migration_file}\n"
                f"Приложение: {app_name}\n"
                f"Подпись проверена: {signature_info['verified']}\n"
                f"Подписант: {signature_info['signed_by']}\n"
                f"Контрольная сумма: {file_checksum}\n"
                f"Время выполнения: {execution_time:.2f} мс\n"
                f"Выполнено запросов: {len(statements)}"
            )
        
        session.commit()
        return True
        
    except SignatureError as e:
        # Ошибка подписи - критическая, не записываем в БД как успешную
        error_msg = str(e)
        logger.critical(error_msg)
        
        # Пытаемся записать информацию об ошибке подписи
        try:
            execution_time = (time.time() - start_time) * 1000
            
            # Используем вычисленную ранее контрольную сумму или пустую строку
            checksum = file_checksum if 'file_checksum' in locals() else 'unknown'
            
            # Проверяем существование записи
            existing = session.execute(
                text("SELECT 1 FROM applied_migrations WHERE name = :name AND name_app = :name_app"),
                {"name": migration_file, "name_app": app_name}
            ).fetchone()
            
            if existing:
                session.execute(
                    text("""
                        UPDATE applied_migrations 
                        SET status = 'error',
                            error_message = :error_message,
                            signature_verified = false,
                            applied_at = NOW()
                        WHERE name = :name AND name_app = :name_app
                    """),
                    {
                        "name": migration_file,
                        "name_app": app_name,
                        "error_message": f"Ошибка подписи: {str(e)}"[:1000]
                    }
                )
            else:
                session.execute(
                    text("""
                        INSERT INTO applied_migrations 
                        (name, name_app, checksum, execution_time_ms, status, error_message, signature_verified) 
                        VALUES (:name, :name_app, :checksum, :execution_time, 'error', :error_message, false)
                    """),
                    {
                        "name": migration_file,
                        "name_app": app_name,
                        "checksum": checksum,
                        "execution_time": execution_time,
                        "error_message": f"Ошибка подписи: {str(e)}"[:1000]
                    }
                )
            session.commit()
        except Exception as db_error:
            logger.error(f"Ошибка записи информации об ошибке подписи: {db_error}")
            session.rollback()
        
        _log_migration_step("Ошибка подписи", error_msg, "critical")
        return False
        
    except Exception as e:
        # Другие ошибки применения миграции
        error_msg = f"Ошибка применения миграции {migration_file}: {str(e)}"
        
        # Записываем информацию об ошибке в БД
        try:
            execution_time = (time.time() - start_time) * 1000
            checksum = file_checksum if 'file_checksum' in locals() else 'unknown'
            
            existing = session.execute(
                text("SELECT 1 FROM applied_migrations WHERE name = :name AND name_app = :name_app"),
                {"name": migration_file, "name_app": app_name}
            ).fetchone()
            
            if existing:
                session.execute(
                    text("""
                        UPDATE applied_migrations 
                        SET checksum = :checksum,
                            execution_time_ms = :execution_time,
                            status = 'error',
                            error_message = :error_message,
                            signature_verified = :signature_verified,
                            signed_by = :signed_by,
                            applied_at = NOW()
                        WHERE name = :name AND name_app = :name_app
                    """),
                    {
                        "name": migration_file,
                        "name_app": app_name,
                        "checksum": checksum,
                        "execution_time": execution_time,
                        "error_message": str(e)[:1000],
                        "signature_verified": signature_info.get('verified', False),
                        "signed_by": signature_info.get('signed_by')
                    }
                )
            else:
                session.execute(
                    text("""
                        INSERT INTO applied_migrations 
                        (name, name_app, checksum, execution_time_ms, status, error_message,
                         signature_verified, signed_by) 
                        VALUES (:name, :name_app, :checksum, :execution_time, 'error', :error_message,
                                :signature_verified, :signed_by)
                    """),
                    {
                        "name": migration_file,
                        "name_app": app_name,
                        "checksum": checksum,
                        "execution_time": execution_time,
                        "error_message": str(e)[:1000],
                        "signature_verified": signature_info.get('verified', False),
                        "signed_by": signature_info.get('signed_by')
                    }
                )
            session.commit()
        except Exception as db_error:
            logger.error(f"Ошибка записи информации об ошибке миграции: {db_error}")
            session.rollback()
        
        _log_migration_step("Ошибка", error_msg, "error")
        return False

@with_db_session
def run_migrations(session) -> List[str]:
    """
    Выполняет все непримененные миграции по очереди.
    Выполняется только один раз. Ожидает готовности БД (FLAG_DB_ACTIVE = 1).
    Устанавливает FLAG_MIGRATION_COMPLETE:
        2 - миграции выполняются
        1 - все миграции успешно применены
        0 - ошибка при выполнении миграций
    """
    global migration_status_cache
    
    # Проверяем, не выполнялись ли уже миграции
    current_flag = get_migration_flag()
    if current_flag == 1:
        logger.debug("Миграции уже успешно выполнены (флаг = 1), пропускаем выполнение")
        return []
    elif current_flag == 2:
        logger.debug("Миграции уже выполняются в другом потоке (флаг = 2), пропускаем")
        return []
    
    # Устанавливаем флаг "выполняется"
    logger.info("Установка флага FLAG_MIGRATION_COMPLETE = 2 (выполняется)")
    set_migration_flag(2)
    
    total_start = time.time()
    applied_migrations = []
    error_occurred = False
    
    try:
        # Ожидаем готовности базы данных
        logger.info("Ожидание готовности базы данных (FLAG_DB_ACTIVE = 1)...")
        if not wait_for_db_flag(max_attempts=30, delay=2.0):
            error_msg = "База данных недоступна после множества попыток, миграции не могут быть выполнены"
            _log_migration_step("Критическая ошибка", error_msg, "critical")
            error_occurred = True
            raise MigrationError(error_msg)
        
        logger.info("База данных готова, запуск миграций")
        
        status_data = _get_migration_status_data(session)
        app_name = status_data['app_name']
        pending = status_data['pending']
        
        _log_migration_step(
            "Запуск процесса миграций",
            f"Приложение: {app_name}\n"
            f"Стратегия: Остановка при первой ошибке\n"
            f"Повторное применение миграций с ошибками"
        )
        
        if not pending:
            _log_migration_step(
                "Нет новых миграций",
                "Все миграции уже применены успешно",
                "info"
            )
            _update_migration_cache(complete=True, has_errors=False, pending_count=0)
            logger.debug("Миграции завершены, кэш обновлен")
            
            # Устанавливаем флаг "успешно"
            logger.info("Установка флага FLAG_MIGRATION_COMPLETE = 1 (успешно)")
            set_migration_flag(1)
            return []
        
        # Применение миграций по порядку
        for migration_file in pending:
            # Логируем тип применения (новая миграция или повторная)
            if migration_file in status_data['applied']:
                prev_status = status_data['applied'][migration_file][2]
                _log_migration_step(
                    "Повторное применение миграции",
                    f"Миграция: {migration_file}\n"
                    f"Предыдущий статус: {prev_status}"
                )
            else:
                _log_migration_step(
                    "Первое применение миграции",
                    f"Миграция: {migration_file}"
                )
            
            success = apply_migration(session, migration_file, app_name)
            if success:
                applied_migrations.append(migration_file)
            else:
                error_msg = f"Миграция {migration_file} завершилась ошибкой. Процесс остановлен."
                _log_migration_step("Критическая ошибка", error_msg, "critical")
                
                # Обновляем кэш с информацией об ошибке
                remaining_pending = len(pending) - len(applied_migrations)
                _update_migration_cache(complete=False, has_errors=True, pending_count=remaining_pending)
                
                error_occurred = True
                raise MigrationError(error_msg, migration_file)
        
        # Если все миграции успешно применены
        total_time = (time.time() - total_start) * 1000
        _update_migration_cache(complete=True, has_errors=False, pending_count=0)
        
        # Устанавливаем флаг "успешно"
        logger.info("Установка флага FLAG_MIGRATION_COMPLETE = 1 (успешно)")
        set_migration_flag(1)
        
        _log_migration_step(
            "Все миграции успешно применены",
            f"Приложение: {app_name}\n"
            f"Кэш миграций обновлен\n"
            f"Применено в этой сессии: {len(applied_migrations)}\n"
            f"Всего проверенных подписей: {len(verified_migrations_cache)}\n"
            f"Общее время: {total_time:.2f} мс"
        )
        
        return applied_migrations
        
    except Exception as e:
        total_time = (time.time() - total_start) * 1000
        _log_migration_step(
            "Процесс миграций завершен с ошибкой",
            f"Применено миграций в сессии: {len(applied_migrations)}\n"
            f"Общее время: {total_time:.2f} мс\n"
            f"Кэш миграций обновлен с информацией об ошибке",
            "critical"
        )
        
        # ВАЖНО: Устанавливаем флаг "ошибка" в любом случае при возникновении исключения
        # Проверяем, не был ли флаг уже установлен в 0
        current_flag = get_migration_flag()
        if current_flag != 0:
            logger.info("Установка флага FLAG_MIGRATION_COMPLETE = 0 (ошибка)")
            try:
                set_migration_flag(0)
            except Exception as flag_error:
                logger.error(f"Не удалось установить флаг ошибки: {flag_error}")
        
        # Пробрасываем исключение дальше
        raise MigrationError(f"Процесс миграций завершен с ошибкой: {str(e)}") from e
    
    finally:
        # Дополнительная страховка: если произошла ошибка, но флаг не 0, устанавливаем его в 0
        if error_occurred:
            try:
                final_flag = get_migration_flag()
                if final_flag != 0:
                    logger.warning(f"Обнаружена ошибка, но флаг = {final_flag}. Принудительная установка FLAG_MIGRATION_COMPLETE = 0")
                    set_migration_flag(0)
            except Exception as final_flag_error:
                logger.error(f"Не удалось установить флаг ошибки в finally блоке: {final_flag_error}")

@with_db_session
def check_migrations_status(session) -> Tuple[bool, str, List[str]]:
    """
    Проверяет статус миграций без их выполнения.
    Использует кэш для избежания лишних запросов к БД.
    """
    global migration_status_cache
    
    # Если статус уже проверен, возвращаем результат из кэша
    if migration_status_cache['checked']:
        pending_count = migration_status_cache['pending_count']
        has_errors = migration_status_cache['has_errors']
        
        if pending_count == 0:
            if not has_errors:
                return (True, "Все миграции применены успешно (кэш)", [])
            else:
                return (False, "Миграции завершены с ошибками (кэш)", [])
        else:
            return (False, f"Ожидают применения {pending_count} миграций (кэш)", [])
    
    try:
        status_data = _get_migration_status_data(session)
        pending = status_data['pending']
        has_errors = status_data['has_errors']
        
        # Обновляем кэш
        _update_migration_cache(
            complete=status_data['complete'],
            has_errors=has_errors,
            pending_count=len(pending)
        )
        
        if len(pending) == 0:
            if not has_errors:
                return (True, "Все миграции применены успешно", [])
            else:
                return (False, "Миграции завершены с ошибками", [])
        else:
            error_count = sum(1 for _, _, status in status_data['applied'].values() if status == 'error')
            success_count = sum(1 for _, _, status in status_data['applied'].values() if status == 'success')
            
            return (False, f"Ожидают применения {len(pending)} миграций (успешных: {success_count}, с ошибками: {error_count})", pending)
            
    except Exception as e:
        error_msg = f"Ошибка проверки статуса миграций: {str(e)}"
        logger.error(error_msg)
        # В случае ошибки не кэшируем результат
        return (False, error_msg, [])

@with_db_session
def is_migration_complete(session) -> bool:
    """
    Проверяет, завершены ли все миграции.
    Использует кэш для избежания лишних запросов к БД.
    """
    global migration_status_cache
    
    # Сначала проверяем флаг миграции
    flag_value = get_migration_flag()
    if flag_value == 1:
        logger.debug("Флаг миграции = 1, миграции успешно завершены")
        return True
    elif flag_value == 0:
        logger.debug("Флаг миграции = 0, миграции завершились ошибкой")
        return False
    elif flag_value == 2:
        logger.debug("Флаг миграции = 2, миграции выполняются")
        return False
    
    # Если статус уже проверен и нет ожидающих миграций, возвращаем результат из кэша
    if migration_status_cache['checked'] and migration_status_cache['pending_count'] == 0:
        logger.debug(f"Используется кэш миграций: complete={migration_status_cache['complete']}, has_errors={migration_status_cache['has_errors']}")
        return migration_status_cache['complete'] and not migration_status_cache['has_errors']
    
    try:
        status_data = _get_migration_status_data(session)
        complete = status_data['complete']
        
        # Обновляем кэш
        _update_migration_cache(
            complete=complete,
            has_errors=status_data['has_errors'],
            pending_count=status_data['pending_count']
        )
        
        logger.debug(f"Статус миграций обновлен в кэше: complete={complete}, has_errors={status_data['has_errors']}, pending_count={status_data['pending_count']}")
        
        return complete
        
    except Exception as e:
        logger.error(f"Ошибка проверки статуса миграций: {str(e)}")
        # В случае ошибки не кэшируем результат, чтобы попробовать снова
        return False

@with_db_session
def get_migration_status(session) -> Dict:
    """
    Возвращает детальный статус миграций в виде словаря
    """
    try:
        status_data = _get_migration_status_data(session)
        applied = status_data['applied']
        
        # Получаем детальную информацию о примененных миграциях
        applied_details = []
        for migration in sorted(applied.keys()):
            checksum, exec_time, status = applied[migration]
            applied_details.append({
                'name': migration,
                'checksum': checksum,
                'execution_time_ms': exec_time,
                'status': status
            })
        
        return {
            'app_name': status_data['app_name'],
            'total_migrations': len(status_data['all_files']),
            'applied_count': len(applied),
            'pending_count': status_data['pending_count'],
            'pending_migrations': status_data['pending'],
            'applied_migrations': applied_details,
            'all_complete': status_data['complete'],
            'has_errors': status_data['has_errors'],
            'migration_flag': get_migration_flag(),
            'verified_migrations_count': len(verified_migrations_cache)
        }
        
    except Exception as e:
        return {
            'app_name': 'unknown',
            'total_migrations': 0,
            'applied_count': 0,
            'pending_count': 0,
            'pending_migrations': [],
            'applied_migrations': [],
            'all_complete': False,
            'has_errors': True,
            'migration_flag': get_migration_flag(),
            'verified_migrations_count': 0,
            'error': str(e)
        }

# ==================== УТИЛИТЫ ДЛЯ РАБОТЫ С ПОДПИСЯМИ ====================

def verify_all_migrations() -> Dict[str, bool]:
    """
    Проверяет подписи всех файлов миграций без их применения.
    Возвращает словарь {имя_файла: результат_проверки}
    """
    results = {}
    migration_files = get_migration_files()
    current_dir = Path(__file__).parent.parent
    migrations_dir = current_dir / 'migrations'
    
    logger.info(f"Проверка подписей {len(migration_files)} файлов миграций...")
    
    for migration_file in migration_files:
        file_path = migrations_dir / migration_file
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()
            
            result = verify_migration_signature(migration_file, sql_content)
            results[migration_file] = result
            
            if result:
                logger.info(f"✓ {migration_file}: подпись действительна")
            else:
                logger.error(f"✗ {migration_file}: подпись недействительна")
                
        except Exception as e:
            logger.error(f"✗ {migration_file}: ошибка проверки - {str(e)}")
            results[migration_file] = False
    
    return results

def get_verification_cache_info() -> Dict[str, Any]:
    """
    Возвращает информацию о кэше проверенных подписей
    """
    return {
        'cached_migrations': list(verified_migrations_cache),
        'cache_size': len(verified_migrations_cache),
        'cache_type': 'verified_migrations'
    }

def clear_verification_cache() -> None:
    """
    Очищает кэш проверенных подписей
    """
    global verified_migrations_cache
    verified_migrations_cache.clear()
    logger.info("Кэш проверенных подписей очищен")
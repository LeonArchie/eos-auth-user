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
    logger.debug(f"НАЧАЛО extract_signature_headers: длина sql_content={len(sql_content)}")
    
    headers = {}
    lines = sql_content.splitlines()
    content_lines = []
    header_pattern = re.compile(r'^--\s*(SIGNATURE|SIGNED_BY|SIGNED_AT|CHECKSUM):\s*(.+)$')
    
    header_count = 0
    for i, line in enumerate(lines):
        match = header_pattern.match(line)
        if match:
            key, value = match.groups()
            headers[key] = value.strip()
            header_count += 1
            logger.debug(f"  Найден заголовок [{i}]: {key} = {value.strip()[:50]}...")
        else:
            content_lines.append(line)
    
    clean_content = '\n'.join(content_lines)
    logger.debug(f"КОНЕЦ extract_signature_headers: найдено заголовков={header_count}, длина clean_content={len(clean_content)}")
    
    return headers, clean_content

def verify_migration_signature(migration_file: str, sql_content: str) -> bool:
    """
    Проверяет подпись SQL-скрипта миграции.
    Возвращает True если подпись действительна, иначе выбрасывает исключение.
    """
    logger.debug(f"=== ПРОВЕРКА ПОДПИСИ: {migration_file} ===")
    logger.debug(f"  Длина sql_content: {len(sql_content)}")
    logger.debug(f"  Первые 200 символов:\n{sql_content[:200]}")
    
    global verified_migrations_cache
    
    # Проверяем кэш
    if migration_file in verified_migrations_cache:
        logger.debug(f"  Миграция {migration_file} уже проверена, используем кэш")
        logger.debug(f"=== КОНЕЦ ПРОВЕРКИ ПОДПИСИ (кэш) ===")
        return True
    
    try:
        # Извлекаем заголовки подписи
        logger.debug("  Шаг 1: Извлечение заголовков подписи")
        headers, clean_content = extract_signature_headers(sql_content)
        logger.debug(f"  Извлеченные заголовки: {list(headers.keys())}")
        
        # Проверяем наличие всех необходимых заголовков
        required_headers = ['SIGNATURE', 'SIGNED_BY', 'SIGNED_AT']
        missing_headers = [h for h in required_headers if h not in headers]
        
        if missing_headers:
            logger.error(f"  Отсутствуют обязательные заголовки: {missing_headers}")
            raise SignatureError(
                f"Отсутствуют обязательные заголовки подписи: {', '.join(missing_headers)}",
                migration_file
            )
        logger.debug(f"  Все обязательные заголовки присутствуют")
        
        # Проверяем контрольную сумму
        if 'CHECKSUM' in headers:
            logger.debug("  Шаг 2: Проверка контрольной суммы")
            calculated_checksum = hashlib.sha256(clean_content.encode('utf-8')).hexdigest()
            logger.debug(f"    Ожидаемая контрольная сумма: {headers['CHECKSUM']}")
            logger.debug(f"    Вычисленная контрольная сумма: {calculated_checksum}")
            
            if calculated_checksum != headers['CHECKSUM']:
                raise SignatureError(
                    f"Контрольная сумма не совпадает. Ожидалось: {headers['CHECKSUM']}, "
                    f"Вычислено: {calculated_checksum}",
                    migration_file
                )
            logger.debug(f"  Контрольная сумма {migration_file} совпадает")
        else:
            logger.debug("  Контрольная сумма отсутствует (необязательный заголовок)")
        
        # Получаем публичный ключ разработчика
        logger.debug("  Шаг 3: Поиск публичного ключа разработчика")
        signed_by = headers['SIGNED_BY']
        logger.debug(f"    Подписант: {signed_by}")
        
        if signed_by not in DEVELOPER_KEYS:
            logger.error(f"    Разработчик '{signed_by}' не найден в хранилище")
            raise SignatureError(
                f"Разработчик '{signed_by}' не найден в хранилище ключей. "
                f"Доступные разработчики: {list(DEVELOPER_KEYS.keys())}",
                migration_file
            )
        logger.debug(f"    Разработчик найден, длина ключа: {len(DEVELOPER_KEYS[signed_by])}")
        
        # Загружаем публичный ключ
        logger.debug("  Шаг 4: Загрузка публичного ключа")
        try:
            public_key_pem = DEVELOPER_KEYS[signed_by].strip()
            logger.debug(f"    PEM ключа (первые 50): {public_key_pem[:50]}...")
            
            public_key = load_pem_public_key(
                public_key_pem.encode('utf-8'),
                backend=default_backend()
            )
            logger.debug(f"    Ключ успешно загружен, тип: {type(public_key).__name__}")
        except Exception as e:
            logger.error(f"    Ошибка загрузки ключа: {str(e)}")
            raise SignatureError(
                f"Ошибка загрузки публичного ключа для {signed_by}: {str(e)}",
                migration_file
            )
        
        # Проверяем тип ключа (ожидаем ECDSA)
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            raise SignatureError(
                f"Неподдерживаемый тип ключа. Ожидался ECDSA, получен {type(public_key).__name__}",
                migration_file
            )
        logger.debug(f"  Тип ключа корректен (ECDSA)")
        
        # Декодируем подпись из base64
        logger.debug("  Шаг 5: Декодирование подписи из base64")
        try:
            signature_b64 = headers['SIGNATURE']
            logger.debug(f"    Подпись (base64, первые 50): {signature_b64[:50]}...")
            signature = base64.b64decode(signature_b64)
            logger.debug(f"    Подпись декодирована, длина: {len(signature)} байт")
        except Exception as e:
            logger.error(f"    Ошибка декодирования: {str(e)}")
            raise SignatureError(
                f"Ошибка декодирования подписи: {str(e)}",
                migration_file
            )
        
        # Подготавливаем данные для проверки
        logger.debug("  Шаг 6: Подготовка данных для проверки подписи")
        verification_data = clean_content.encode('utf-8')
        logger.debug(f"    Длина данных для проверки: {len(verification_data)} байт")
        logger.debug(f"    Первые 100 байт данных: {verification_data[:100]}")
        
        # Проверяем подпись
        logger.debug("  Шаг 7: Проверка подписи через cryptography")
        try:
            public_key.verify(
                signature,
                verification_data,
                ec.ECDSA(hashes.SHA256())
            )
            logger.info(f"✓ Подпись миграции {migration_file} действительна (подписано: {signed_by})")
            
            # Добавляем в кэш проверенных миграций
            verified_migrations_cache.add(migration_file)
            logger.debug(f"  Миграция добавлена в кэш проверенных")
            logger.debug(f"=== КОНЕЦ ПРОВЕРКИ ПОДПИСИ (успешно) ===")
            return True
            
        except InvalidSignature:
            logger.error(f"  Недействительная подпись для миграции")
            raise SignatureError(
                f"Недействительная подпись для миграции {migration_file}",
                migration_file
            )
            
    except SignatureError:
        logger.debug(f"=== КОНЕЦ ПРОВЕРКИ ПОДПИСИ (SignatureError) ===")
        raise
    except Exception as e:
        logger.debug(f"=== КОНЕЦ ПРОВЕРКИ ПОДПИСИ (неожиданная ошибка) ===")
        raise SignatureError(
            f"Неожиданная ошибка при проверке подписи: {str(e)}",
            migration_file
        )

def verify_migration_file(migration_file: str, file_path: Path) -> bool:
    """
    Проверяет файл миграции на наличие действительной подписи.
    """
    logger.debug(f"ПРОВЕРКА ФАЙЛА МИГРАЦИИ: {migration_file}, путь: {file_path}")
    
    global verified_migrations_cache
    
    # Проверяем кэш
    if migration_file in verified_migrations_cache:
        logger.debug(f"  Миграция {migration_file} уже проверена ранее (кэш)")
        logger.debug(f"  Результат: True (из кэша)")
        return True
    
    try:
        # Читаем содержимое файла
        logger.debug(f"  Чтение файла {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        logger.debug(f"  Файл прочитан, размер: {len(sql_content)} байт")
        
        # Проверяем подпись
        logger.debug(f"  Вызов verify_migration_signature для {migration_file}")
        result = verify_migration_signature(migration_file, sql_content)
        logger.debug(f"  Результат verify_migration_signature: {result}")
        
        # Если проверка прошла успешно, добавляем в кэш
        if result:
            verified_migrations_cache.add(migration_file)
            logger.debug(f"  Миграция добавлена в кэш")
        
        logger.debug(f"  Конец проверки файла, результат: {result}")
        return result
        
    except SignatureError as e:
        logger.error(f"  SignatureError при проверке файла: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"  Ошибка при проверке файла миграции {migration_file}: {str(e)}")
        return False

# ==================== ДЕКОРАТОРЫ И ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def with_db_session(func: Callable) -> Callable:
    """Декоратор для автоматического получения сессии БД"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.debug(f"ДЕКОРАТОР with_db_session: вызов {func.__name__}")
        from maintenance.database_connector import get_db_connector
        connector = get_db_connector()
        logger.debug(f"  Получен connector: {connector}")
        with connector.get_session() as session:
            logger.debug(f"  Получена сессия: {session}")
            result = func(session, *args, **kwargs)
            logger.debug(f"  Функция {func.__name__} выполнена, результат: {result}")
            return result
    return wrapper

def _log_migration_step(step: str, details: str = "", level: str = "info") -> None:
    """Унифицированное логирование шагов миграции"""
    log_method = getattr(logger, level.lower(), logger.info)
    
    # Для debug уровня добавляем больше деталей
    if level.lower() == "debug":
        log_method(f"МИГРАЦИЯ(DEBUG): {step} - {details}")
    else:
        log_method(f"МИГРАЦИЯ: {step} {details}")

def _get_pending_migrations(applied: Dict, all_files: set) -> List[str]:
    """Получить список ожидающих миграций (не примененные или с ошибками)"""
    logger.debug(f"ПОЛУЧЕНИЕ ОЖИДАЮЩИХ МИГРАЦИЙ: applied={len(applied)}, all_files={len(all_files)}")
    
    pending = []
    for migration_file in sorted(all_files):
        if migration_file not in applied:
            logger.debug(f"  {migration_file}: не применена")
            pending.append(migration_file)
        elif (migration_file in applied and 
              applied[migration_file][2] == 'error'):
            logger.debug(f"  {migration_file}: была с ошибкой")
            pending.append(migration_file)
    
    logger.debug(f"  Найдено ожидающих: {len(pending)}")
    return pending

def _update_migration_cache(complete: bool, has_errors: bool, pending_count: int) -> None:
    """Обновить кэш статуса миграций"""
    global migration_status_cache
    logger.debug(f"ОБНОВЛЕНИЕ КЭША МИГРАЦИЙ: было={migration_status_cache}")
    
    migration_status_cache = {
        'complete': complete,
        'checked': True,
        'has_errors': has_errors,
        'pending_count': pending_count
    }
    
    logger.debug(f"  стало={migration_status_cache}")

def _get_migration_status_data(session) -> Dict[str, Any]:
    """Базовая функция для получения данных о статусе миграций"""
    logger.debug(f"ПОЛУЧЕНИЕ ДАННЫХ О СТАТУСЕ МИГРАЦИЙ")
    
    app_name = get_app_name()
    logger.debug(f"  app_name={app_name}")
    
    check_migrations_table(session)
    applied = get_applied_migrations(session, app_name)
    logger.debug(f"  applied={len(applied)}")
    
    all_files = set(get_migration_files())
    logger.debug(f"  all_files={len(all_files)}")
    
    pending = _get_pending_migrations(applied, all_files)
    has_errors = any(m[2] == 'error' for m in applied.values())
    
    result = {
        'app_name': app_name,
        'applied': applied,
        'all_files': all_files,
        'pending': pending,
        'has_errors': has_errors,
        'pending_count': len(pending),
        'complete': len(pending) == 0 and not has_errors
    }
    
    logger.debug(f"  complete={result['complete']}, has_errors={has_errors}, pending_count={len(pending)}")
    logger.debug(f"  pending={pending}")
    
    return result

# ==================== ОСНОВНЫЕ ФУНКЦИИ ====================

def get_app_name() -> str:
    """
    Получает имя приложения из файла global.conf
    """
    logger.debug(f"ПОЛУЧЕНИЕ ИМЕНИ ПРИЛОЖЕНИЯ ИЗ global.conf")
    
    try:
        current_dir = Path(__file__).parent.parent
        config_file_path = current_dir / 'global.conf'
        
        logger.debug(f"  Текущая директория: {current_dir}")
        logger.debug(f"  Путь к конфигу: {config_file_path}")
        logger.debug(f"  Файл существует: {config_file_path.exists()}")
        
        if not config_file_path.exists():
            error_msg = f"Файл конфигурации не найден: {config_file_path}"
            _log_migration_step("Ошибка", error_msg, "error")
            raise MigrationError(error_msg)

        with open(config_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            logger.debug(f"  Прочитано строк: {len(lines)}")
            
            for i, line in enumerate(lines):
                line = line.strip()
                if line.startswith('NAME_APP='):
                    app_name = line.split('=', 1)[1].strip()
                    logger.debug(f"  Найдена строка [{i}]: {line}")
                    logger.debug(f"  app_name={app_name}")
                    
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
    logger.debug(f"ПОЛУЧЕНИЕ СПИСКА ФАЙЛОВ МИГРАЦИЙ")
    
    try:
        current_dir = Path(__file__).parent.parent
        migrations_dir = current_dir / 'migrations'
        
        logger.debug(f"  Директория миграций: {migrations_dir}")
        logger.debug(f"  Директория существует: {migrations_dir.exists()}")
        
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
                logger.debug(f"  Найден SQL файл: {f.name}")
                
                if re.match(r'^\d{3}-.+\.sql$', f.name):
                    valid_files.append(f.name)
                    logger.debug(f"    Валидная миграция: {f.name}")
                else:
                    logger.debug(f"    Невалидный формат имени: {f.name}")

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
        logger.debug(f"  Отсортированные файлы: {sorted_files}")
        
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
    logger.debug(f"ПРОВЕРКА ТАБЛИЦЫ applied_migrations")
    
    try:
        _log_migration_step("Проверка таблицы applied_migrations")
        
        # Проверка существования таблица
        logger.debug("  Выполнение SQL запроса для проверки существования таблицы")
        result = session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'applied_migrations'
            )
        """))
        exists = result.scalar()
        logger.debug(f"  Таблица существует: {exists}")
        
        if exists:
            _log_migration_step("Таблица существует", "Продолжение без создания")
            return

        _log_migration_step("Создание таблицы applied_migrations")
        logger.debug("  Выполнение CREATE TABLE")
        
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
        logger.debug("  Таблица успешно создана")
        
        _log_migration_step("Таблица создана", "Успешно создана таблица applied_migrations")
        
    except SQLAlchemyError as e:
        session.rollback()
        error_msg = f"Ошибка создания таблицы миграций: {str(e)}"
        logger.error(f"  SQLAlchemyError: {error_msg}")
        _log_migration_step("Ошибка SQL", error_msg, "error")
        raise MigrationError(error_msg) from e
    except Exception as e:
        session.rollback()
        error_msg = f"Неожиданная ошибка при работе с таблицей миграций: {str(e)}"
        logger.error(f"  Exception: {error_msg}")
        _log_migration_step("Критическая ошибка", error_msg, "critical")
        raise MigrationError(error_msg) from e

def get_applied_migrations(session, app_name: str) -> Dict[str, Tuple[str, float, str]]:
    """
    Получаем список примененных миграций для конкретного приложения
    """
    logger.debug(f"ПОЛУЧЕНИЕ ПРИМЕНЕННЫХ МИГРАЦИЙ: app_name={app_name}")
    
    try:
        _log_migration_step("Получение списка примененных миграций", f"Приложение: {app_name}")
        
        logger.debug("  Выполнение SQL запроса SELECT")
        result = session.execute(text("""
            SELECT name, checksum, execution_time_ms, status
            FROM applied_migrations 
            WHERE name_app = :app_name
            ORDER BY applied_at
        """), {"app_name": app_name})
        
        rows = result.fetchall()
        logger.debug(f"  Получено строк: {len(rows)}")
        
        migrations = {}
        for i, row in enumerate(rows):
            migrations[row[0]] = (row[1], row[2], row[3])
            logger.debug(f"  [{i}] {row[0]}: status={row[3]}, checksum={row[1][:10]}...")
        
        success_count = len([m for m in migrations.values() if m[2] == 'success'])
        error_count = len([m for m in migrations.values() if m[2] == 'error'])
        
        _log_migration_step(
            "Полученные миграции",
            f"Найдено примененных миграций: {len(migrations)}\n"
            f"Успешных: {success_count}\n"
            f"С ошибками: {error_count}"
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
    logger.debug(f"ВЫЧИСЛЕНИЕ КОНТРОЛЬНОЙ СУММЫ: {file_path.name}")
    
    try:
        _log_migration_step("Вычисление контрольной суммы", f"Файл: {file_path.name}")
        
        with open(file_path, 'rb') as f:
            content = f.read()
            logger.debug(f"  Прочитано байт: {len(content)}")
            
            checksum = hashlib.sha256(content).hexdigest()
            logger.debug(f"  SHA-256: {checksum}")
            
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
    logger.debug(f"РАЗБОР SQL НА ЗАПРОСЫ: длина sql={len(sql)}")
    
    _log_migration_step("Разбор SQL на отдельные запросы")
    
    statements = []
    current = ""
    in_dollar_quote = False
    dollar_tag = ""
    
    i = 0
    n = len(sql)
    
    dollar_quote_count = 0
    while i < n:
        char = sql[i]
        
        # Обработка комментариев
        if not in_dollar_quote and char == '-' and i + 1 < n and sql[i+1] == '-':
            # Пропускаем однострочный комментарий
            comment_start = i
            while i < n and sql[i] != '\n':
                i += 1
            comment = sql[comment_start:i]
            logger.debug(f"  Пропущен комментарий: {comment[:30]}...")
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
                dollar_quote_count += 1
                logger.debug(f"  Начало dollar-quoted строки [{dollar_quote_count}], tag='{tag}', позиция {i}")
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
                logger.debug(f"  Конец dollar-quoted строки [{dollar_quote_count}], tag='{tag}', позиция {i}")
                current += sql[i:j+1]
                i = j + 1
                continue
        
        # Если не в dollar-quoted строке, ищем точку с запятой
        if char == ';' and not in_dollar_quote:
            current += char
            if current.strip():
                statements.append(current.strip())
                logger.debug(f"  Добавлен запрос #{len(statements)}: {current[:50]}...")
            current = ""
            i += 1
            continue
        
        current += char
        i += 1
    
    # Добавляем последний statement если он есть
    if current.strip():
        statements.append(current.strip())
        logger.debug(f"  Добавлен последний запрос #{len(statements)}: {current[:50]}...")
    
    _log_migration_step(
        "Результат разбора SQL",
        f"Всего запросов: {len(statements)}\n"
        f"Пример запроса: {statements[0][:100] + '...' if statements else 'нет'}"
    )
    
    logger.debug(f"  ИТОГО: найдено {len(statements)} запросов")
    return statements

def apply_migration(session, migration_file: str, app_name: str) -> bool:
    """
    Применяет одну миграцию. Возвращает True если успешно, False если ошибка.
    В случае ошибки выполняется откат всех изменений этой миграции.
    Если миграция уже была применена с ошибкой, выполняется повторная попытка.
    Перед применением проверяется цифровая подпись миграции.
    """
    logger.debug(f"=== ПРИМЕНЕНИЕ МИГРАЦИИ: {migration_file} ===")
    logger.debug(f"  app_name={app_name}")
    
    start_time = time.time()
    current_dir = Path(__file__).parent.parent
    file_path = current_dir / 'migrations' / migration_file
    logger.debug(f"  file_path={file_path}")
    logger.debug(f"  файл существует: {file_path.exists()}")
    
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
        logger.debug("  Шаг 1: Вычисление контрольной суммы")
        file_checksum = calculate_checksum(file_path)
        
        # Чтение содержимого файла для проверки подписи
        logger.debug("  Шаг 2: Чтение содержимого файла")
        with open(file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        logger.debug(f"    Прочитано {len(sql_content)} символов")
        
        # Извлекаем информацию о подписи для логирования
        logger.debug("  Шаг 3: Извлечение заголовков подписи")
        headers, clean_content = extract_signature_headers(sql_content)
        if 'SIGNED_BY' in headers:
            signature_info['signed_by'] = headers['SIGNED_BY']
            logger.debug(f"    signed_by={headers['SIGNED_BY']}")
        if 'SIGNED_AT' in headers:
            signature_info['signed_at'] = headers['SIGNED_AT']
            logger.debug(f"    signed_at={headers['SIGNED_AT']}")
        
        # Проверяем подпись миграции
        _log_migration_step(
            "Проверка подписи",
            f"Файл: {migration_file}\n"
            f"Подписант: {signature_info['signed_by'] or 'неизвестен'}\n"
            f"Время подписи: {signature_info['signed_at'] or 'неизвестно'}"
        )
        
        logger.debug("  Шаг 4: Проверка подписи через verify_migration_signature")
        if not verify_migration_signature(migration_file, sql_content):
            error_msg = f"Недействительная подпись миграции {migration_file}"
            _log_migration_step("Ошибка подписи", error_msg, "error")
            raise SignatureError(error_msg, migration_file)
        
        signature_info['verified'] = True
        _log_migration_step("✓ Подпись действительна", f"Миграция {migration_file} прошла проверку")
        
        # Проверяем, существует ли уже запись о миграции (включая статус error)
        logger.debug("  Шаг 5: Проверка существующей записи в БД")
        existing_migration = session.execute(
            text("""
                SELECT status, checksum 
                FROM applied_migrations 
                WHERE name = :name AND name_app = :name_app
            """),
            {"name": migration_file, "name_app": app_name}
        ).fetchone()
        
        if existing_migration:
            logger.debug(f"    Существующая запись: status={existing_migration[0]}, checksum={existing_migration[1][:10]}...")
        else:
            logger.debug("    Запись не существует")
        
        # Если миграция уже существует со статусом error, выполняем UPDATE вместо INSERT
        is_retry = existing_migration and existing_migration[0] == 'error'
        logger.debug(f"    is_retry={is_retry}")
        
        if is_retry:
            _log_migration_step(
                "Повторное применение миграции",
                f"Миграция {migration_file} ранее завершилась ошибкой\n"
                f"Выполняется повторная попытка применения"
            )
        
        # Разбиение на отдельные запросы
        logger.debug("  Шаг 6: Разбор SQL на запросы")
        statements = split_sql_statements(clean_content)
        logger.debug(f"    Получено запросов: {len(statements)}")
        
        # Выполнение каждого запроса
        logger.debug("  Шаг 7: Выполнение запросов")
        for i, query in enumerate(statements, 1):
            query_start = time.time()
            try:
                logger.debug(f"    Выполнение запроса {i}/{len(statements)}")
                logger.debug(f"    Текст запроса (первые 200):\n{query[:200]}")
                
                session.execute(text(query))
                
                query_time = (time.time() - query_start) * 1000
                logger.debug(f"    Запрос {i} выполнен за {query_time:.2f} мс")
            except Exception as e:
                logger.error(f"    Ошибка в запросе {i}:")
                logger.error(f"    Текст запроса с ошибкой (первые 500):\n{query[:500]}...")
                logger.error(f"    Полная ошибка: {str(e)}")
                # При ошибке откатываем всю транзакцию
                session.rollback()
                logger.debug("    Транзакция откачена")
                raise
        
        # Фиксация миграции в БД
        logger.debug("  Шаг 8: Фиксация миграции в БД")
        execution_time = (time.time() - start_time) * 1000
        logger.debug(f"    Общее время выполнения: {execution_time:.2f} мс")
        
        if is_retry:
            # Обновляем существующую запись с информацией о подписи
            logger.debug("    Выполнение UPDATE для существующей записи (error -> success)")
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
            logger.debug("    Выполнение INSERT для новой записи")
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
        logger.debug("  Транзакция закоммичена")
        logger.debug(f"=== ПРИМЕНЕНИЕ МИГРАЦИИ ЗАВЕРШЕНО (успешно) ===")
        return True
        
    except SignatureError as e:
        # Ошибка подписи - критическая, не записываем в БД как успешную
        error_msg = str(e)
        logger.critical(error_msg)
        logger.debug(f"  SignatureError: {error_msg}")
        
        # Пытаемся записать информацию об ошибке подписи
        try:
            execution_time = (time.time() - start_time) * 1000
            
            # Используем вычисленную ранее контрольную сумму или пустую строку
            checksum = file_checksum if 'file_checksum' in locals() else 'unknown'
            
            # Проверяем существование записи
            logger.debug("  Попытка записи информации об ошибке подписи в БД")
            existing = session.execute(
                text("SELECT 1 FROM applied_migrations WHERE name = :name AND name_app = :name_app"),
                {"name": migration_file, "name_app": app_name}
            ).fetchone()
            
            if existing:
                logger.debug("    Обновление существующей записи с ошибкой подписи")
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
                logger.debug("    Создание новой записи с ошибкой подписи")
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
            logger.debug("  Информация об ошибке подписи сохранена в БД")
        except Exception as db_error:
            logger.error(f"  Ошибка записи информации об ошибке подписи: {db_error}")
            session.rollback()
        
        _log_migration_step("Ошибка подписи", error_msg, "critical")
        logger.debug(f"=== ПРИМЕНЕНИЕ МИГРАЦИИ ЗАВЕРШЕНО (SignatureError) ===")
        return False
        
    except Exception as e:
        # Другие ошибки применения миграции
        error_msg = f"Ошибка применения миграции {migration_file}: {str(e)}"
        logger.error(f"  Exception: {error_msg}")
        
        # Записываем информацию об ошибке в БД
        try:
            execution_time = (time.time() - start_time) * 1000
            checksum = file_checksum if 'file_checksum' in locals() else 'unknown'
            
            logger.debug("  Попытка записи информации об ошибке в БД")
            existing = session.execute(
                text("SELECT 1 FROM applied_migrations WHERE name = :name AND name_app = :name_app"),
                {"name": migration_file, "name_app": app_name}
            ).fetchone()
            
            if existing:
                logger.debug("    Обновление существующей записи с ошибкой")
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
                logger.debug("    Создание новой записи с ошибкой")
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
            logger.debug("  Информация об ошибке сохранена в БД")
        except Exception as db_error:
            logger.error(f"  Ошибка записи информации об ошибке миграции: {db_error}")
            session.rollback()
        
        _log_migration_step("Ошибка", error_msg, "error")
        logger.debug(f"=== ПРИМЕНЕНИЕ МИГРАЦИИ ЗАВЕРШЕНО (ошибка) ===")
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
    logger.debug(f"=== ЗАПУСК run_migrations ===")
    
    global migration_status_cache
    
    # Проверяем, не выполнялись ли уже миграции
    current_flag = get_migration_flag()
    logger.debug(f"  Текущий флаг миграции: {current_flag}")
    
    if current_flag == 1:
        logger.debug("  Миграции уже успешно выполнены (флаг = 1), пропускаем выполнение")
        return []
    elif current_flag == 2:
        logger.debug("  Миграции уже выполняются в другом потоке (флаг = 2), пропускаем")
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
        logger.debug("  Вызов wait_for_db_flag(max_attempts=30, delay=2.0)")
        
        if not wait_for_db_flag(max_attempts=30, delay=2.0):
            error_msg = "База данных недоступна после множества попыток, миграции не могут быть выполнены"
            _log_migration_step("Критическая ошибка", error_msg, "critical")
            error_occurred = True
            raise MigrationError(error_msg)
        
        logger.info("База данных готова, запуск миграций")
        
        logger.debug("  Получение статуса миграций")
        status_data = _get_migration_status_data(session)
        app_name = status_data['app_name']
        pending = status_data['pending']
        
        logger.debug(f"  app_name={app_name}")
        logger.debug(f"  pending={pending}")
        
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
            logger.debug("  Миграции завершены, кэш обновлен")
            
            # Устанавливаем флаг "успешно"
            logger.info("Установка флага FLAG_MIGRATION_COMPLETE = 1 (успешно)")
            set_migration_flag(1)
            return []
        
        # Применение миграций по порядку
        for i, migration_file in enumerate(pending, 1):
            logger.debug(f"  Обработка миграции {i}/{len(pending)}: {migration_file}")
            
            # Логируем тип применения (новая миграция или повторная)
            if migration_file in status_data['applied']:
                prev_status = status_data['applied'][migration_file][2]
                _log_migration_step(
                    "Повторное применение миграции",
                    f"Миграция: {migration_file}\n"
                    f"Предыдущий статус: {prev_status}"
                )
                logger.debug(f"    Предыдущий статус: {prev_status}")
            else:
                _log_migration_step(
                    "Первое применение миграции",
                    f"Миграция: {migration_file}"
                )
                logger.debug(f"    Первое применение")
            
            logger.debug(f"  Вызов apply_migration для {migration_file}")
            success = apply_migration(session, migration_file, app_name)
            logger.debug(f"  Результат apply_migration: {success}")
            
            if success:
                applied_migrations.append(migration_file)
                logger.debug(f"  Миграция добавлена в список примененных")
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
        
        logger.debug(f"=== ЗАВЕРШЕНИЕ run_migrations (успешно) ===")
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
        logger.debug(f"  Флаг миграции перед установкой ошибки: {current_flag}")
        
        if current_flag != 0:
            logger.info("Установка флага FLAG_MIGRATION_COMPLETE = 0 (ошибка)")
            try:
                set_migration_flag(0)
                logger.debug("  Флаг ошибки установлен")
            except Exception as flag_error:
                logger.error(f"  Не удалось установить флаг ошибки: {flag_error}")
        
        # Пробрасываем исключение дальше
        logger.debug(f"=== ЗАВЕРШЕНИЕ run_migrations (исключение) ===")
        raise MigrationError(f"Процесс миграций завершен с ошибкой: {str(e)}") from e
    
    finally:
        # Дополнительная страховка: если произошла ошибка, но флаг не 0, устанавливаем его в 0
        if error_occurred:
            try:
                final_flag = get_migration_flag()
                logger.debug(f"  Флаг в finally блоке: {final_flag}")
                
                if final_flag != 0:
                    logger.warning(f"Обнаружена ошибка, но флаг = {final_flag}. Принудительная установка FLAG_MIGRATION_COMPLETE = 0")
                    set_migration_flag(0)
                    logger.debug("  Принудительный флаг ошибки установлен")
            except Exception as final_flag_error:
                logger.error(f"  Не удалось установить флаг ошибки в finally блоке: {final_flag_error}")

@with_db_session
def check_migrations_status(session) -> Tuple[bool, str, List[str]]:
    """
    Проверяет статус миграций без их выполнения.
    Использует кэш для избежания лишних запросов к БД.
    """
    logger.debug(f"=== ПРОВЕРКА СТАТУСА МИГРАЦИЙ ===")
    
    global migration_status_cache
    
    logger.debug(f"  Текущий кэш: {migration_status_cache}")
    
    # Если статус уже проверен, возвращаем результат из кэша
    if migration_status_cache['checked']:
        pending_count = migration_status_cache['pending_count']
        has_errors = migration_status_cache['has_errors']
        
        logger.debug(f"  Используем кэш: pending_count={pending_count}, has_errors={has_errors}")
        
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
        
        logger.debug(f"  Данные из БД: pending={pending}, has_errors={has_errors}")
        
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
            
            result_msg = f"Ожидают применения {len(pending)} миграций (успешных: {success_count}, с ошибками: {error_count})"
            logger.debug(f"  Результат: {result_msg}")
            
            return (False, result_msg, pending)
            
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
    logger.debug(f"=== ПРОВЕРКА is_migration_complete ===")
    
    global migration_status_cache
    
    # Сначала проверяем флаг миграции
    flag_value = get_migration_flag()
    logger.debug(f"  Флаг миграции: {flag_value}")
    
    if flag_value == 1:
        logger.debug("  Флаг миграции = 1, миграции успешно завершены")
        return True
    elif flag_value == 0:
        logger.debug("  Флаг миграции = 0, миграции завершились ошибкой")
        return False
    elif flag_value == 2:
        logger.debug("  Флаг миграции = 2, миграции выполняются")
        return False
    
    # Если статус уже проверен и нет ожидающих миграций, возвращаем результат из кэша
    if migration_status_cache['checked'] and migration_status_cache['pending_count'] == 0:
        logger.debug(f"  Используется кэш: complete={migration_status_cache['complete']}, has_errors={migration_status_cache['has_errors']}")
        return migration_status_cache['complete'] and not migration_status_cache['has_errors']
    
    try:
        status_data = _get_migration_status_data(session)
        complete = status_data['complete']
        
        logger.debug(f"  Данные из БД: complete={complete}")
        
        # Обновляем кэш
        _update_migration_cache(
            complete=complete,
            has_errors=status_data['has_errors'],
            pending_count=status_data['pending_count']
        )
        
        logger.debug(f"  Кэш обновлен, результат: {complete}")
        
        return complete
        
    except Exception as e:
        logger.error(f"  Ошибка проверки статуса миграций: {str(e)}")
        # В случае ошибки не кэшируем результат, чтобы попробовать снова
        return False

@with_db_session
def get_migration_status(session) -> Dict:
    """
    Возвращает детальный статус миграций в виде словаря
    """
    logger.debug(f"=== ПОЛУЧЕНИЕ ДЕТАЛЬНОГО СТАТУСА МИГРАЦИЙ ===")
    
    try:
        status_data = _get_migration_status_data(session)
        applied = status_data['applied']
        
        logger.debug(f"  status_data: complete={status_data['complete']}, has_errors={status_data['has_errors']}")
        logger.debug(f"  pending={status_data['pending']}")
        
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
            logger.debug(f"    {migration}: status={status}, exec_time={exec_time}")
        
        result = {
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
        
        logger.debug(f"  Результат: total={result['total_migrations']}, applied={result['applied_count']}, pending={result['pending_count']}")
        logger.debug(f"  verified_migrations_cache size={result['verified_migrations_count']}")
        
        return result
        
    except Exception as e:
        logger.error(f"  Ошибка получения статуса: {str(e)}")
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
    logger.debug(f"=== ПРОВЕРКА ВСЕХ МИГРАЦИЙ ===")
    
    results = {}
    migration_files = get_migration_files()
    current_dir = Path(__file__).parent.parent
    migrations_dir = current_dir / 'migrations'
    
    logger.info(f"Проверка подписей {len(migration_files)} файлов миграций...")
    
    for i, migration_file in enumerate(migration_files, 1):
        logger.debug(f"  [{i}/{len(migration_files)}] Проверка {migration_file}")
        file_path = migrations_dir / migration_file
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()
                logger.debug(f"    Файл прочитан, размер={len(sql_content)}")
            
            result = verify_migration_signature(migration_file, sql_content)
            results[migration_file] = result
            
            if result:
                logger.info(f"✓ {migration_file}: подпись действительна")
            else:
                logger.error(f"✗ {migration_file}: подпись недействительна")
                
        except Exception as e:
            logger.error(f"✗ {migration_file}: ошибка проверки - {str(e)}")
            results[migration_file] = False
    
    valid_count = sum(1 for r in results.values() if r)
    logger.debug(f"  ИТОГО: проверено={len(results)}, действительных={valid_count}, недействительных={len(results)-valid_count}")
    
    return results

def get_verification_cache_info() -> Dict[str, Any]:
    """
    Возвращает информацию о кэше проверенных подписей
    """
    logger.debug(f"=== ПОЛУЧЕНИЕ ИНФОРМАЦИИ О КЭШЕ ПОДПИСЕЙ ===")
    
    result = {
        'cached_migrations': list(verified_migrations_cache),
        'cache_size': len(verified_migrations_cache),
        'cache_type': 'verified_migrations'
    }
    
    logger.debug(f"  cache_size={result['cache_size']}")
    logger.debug(f"  cached_migrations={result['cached_migrations']}")
    
    return result

def clear_verification_cache() -> None:
    """
    Очищает кэш проверенных подписей
    """
    global verified_migrations_cache
    logger.debug(f"=== ОЧИСТКА КЭША ПОДПИСЕЙ ===")
    logger.debug(f"  Текущий размер кэша: {len(verified_migrations_cache)}")
    logger.debug(f"  Содержимое кэша: {verified_migrations_cache}")
    
    verified_migrations_cache.clear()
    
    logger.info("Кэш проверенных подписей очищен")
    logger.debug(f"  Размер после очистки: {len(verified_migrations_cache)}")
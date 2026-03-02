# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import threading
import sys
from flask import Flask

from handlers.gate import init_gate
from handlers.module_id_injector import ModuleIDInjector
from handlers.rqid_injector import RQIDInjector
from handlers.incoming_logger import IncomingRequestLogger
from handlers.outgoing_logger import OutgoingRequestLogger
from maintenance.logging_config import setup_logging
from maintenance.database_connector import initialize_database, get_database_flag
from maintenance.migration import run_migrations
from maintenance.app_blueprint import register_blueprints, register_error_handlers
from maintenance.global_flags import (get_all_flags,
    update_app_config_with_flags, init_all_flags)
from maintenance.wait_for_flag import wait_for_global_flag  # Импортируем функцию

logger = setup_logging()


def create_app():
    """Создание и инициализация Flask приложения"""
    app = Flask(__name__)
    
    # Инициализация флагов при запуске
    init_all_flags()
    
    # Сохраняем флаги в конфигурации Flask для обратной совместимости
    update_app_config_with_flags(app)
    
    logger.info(f"Статус конфигураций: {get_all_flags()}")

    # Инициализация логгеров
    incoming_logger = IncomingRequestLogger(app)
    outgoing_logger = OutgoingRequestLogger()
    
    # Сохраняем логгеры в конфигурации приложения для доступа из других модулей
    app.config['INCOMING_LOGGER'] = incoming_logger
    app.config['OUTGOING_LOGGER'] = outgoing_logger
    
    # ИНИЦИАЛИЗАЦИЯ ШЛЮЗА - ДОЛЖНА БЫТЬ ДО ВСЕХ ДРУГИХ КОМПОНЕНТОВ
    init_gate(app)
    
    # Инициализация компонентов приложения
    try:
        initialize_components()
    except SystemExit:
        # Пробрасываем SystemExit дальше
        raise
    except Exception as e:
        logger.critical(f"Критическая ошибка при инициализации компонентов: {e}")
        sys.exit(1)
    
    # Запуск миграций в фоновом режиме
    start_migrations_background()
    
    # Регистрация blueprint'ов
    register_blueprints(app)

    # Регистрация обработчиков ошибок
    register_error_handlers(app)
    
    logger.info("Приложение успешно инициализировано")
    return app


def initialize_components():
    """Инициализация компонентов приложения с проверкой флага глобальной конфигурации"""
    try:
        logger.info("Инициализация базы данных...")
        
        # Проверяем флаг глобальной конфигурации с помощью новой функции
        if not wait_for_global_flag(max_attempts=10, delay=10.0):
            logger.critical("Глобальный сервис конфигураций недоступен, невозможно инициализировать БД")
            sys.exit(1)
        
        # Пытаемся инициализировать БД
        initialize_database()
        
        # Проверяем, что БД действительно инициализирована
        db_flag = get_database_flag()
        if db_flag != 1:
            logger.critical(f"База данных не инициализирована (флаг = {db_flag})")
            sys.exit(1)
        
        logger.info("База данных успешно инициализирована")
        
    except SystemExit:
        # Пробрасываем SystemExit дальше
        raise
    except Exception as e:
        logger.critical(f"Ошибка инициализации базы данных: {e}")
        sys.exit(1)


def start_migrations_background():
    """Запуск миграций в фоновом режиме"""
    def run_migrations_background():
        try:
            # Проверяем, что БД доступна перед запуском миграций
            db_flag = get_database_flag()
            if db_flag != 1:
                logger.error("База данных недоступна, миграции не будут выполнены")
                return
            
            logger.info("Запуск миграций базы данных...")
            applied_migrations = run_migrations()
            if applied_migrations:
                logger.info(f"Миграции успешно применены: {applied_migrations}")
            else:
                logger.info("Нет новых миграций для применения")
        except Exception as e:
            logger.error(f"Ошибка выполнения миграций: {e}")

    migration_thread = threading.Thread(target=run_migrations_background, daemon=True)
    migration_thread.start()
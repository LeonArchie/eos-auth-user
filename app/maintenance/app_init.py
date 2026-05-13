# maintenance/app_init.py
# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import sys
from flask import Flask

from handlers.gate import init_gate

from handlers.incoming_logger import IncomingRequestLogger
from handlers.outgoing_logger import OutgoingRequestLogger
from handlers.module_id_injector import inject_module_id_to_requests
from handlers.rqid_injector import inject_rqid
from maintenance.logging_config import setup_logging
from maintenance.database_connector import initialize_database, is_database_initialized
from maintenance.app_blueprint import register_blueprints, register_error_handlers

logger = setup_logging()


def create_app():
    """Создание и инициализация Flask приложения"""
    app = Flask(__name__)

    # Инициализация логгеров
    incoming_logger = IncomingRequestLogger(app)
    outgoing_logger = OutgoingRequestLogger()

    # Сохраняем логгеры в конфигурации приложения для доступа из других модулей
    app.config['INCOMING_LOGGER'] = incoming_logger
    app.config['OUTGOING_LOGGER'] = outgoing_logger

    # ИНИЦИАЛИЗАЦИЯ ИНЖЕКТОРОВ - ДОЛЖНА БЫТЬ ДО ШЛЮЗА
    # Инъекция MODULE-ID во все исходящие requests запросы
    inject_module_id_to_requests()
    logger.info("ModuleIDInjector: глобальная инъекция MODULE-ID выполнена")
    
    # Инъекция Rqid (UUID) во все исходящие requests запросы
    inject_rqid()
    logger.info("RQIDInjector: глобальная инъекция rqid выполнена")

    # ИНИЦИАЛИЗАЦИЯ ШЛЮЗА - ДОЛЖНА БЫТЬ ДО ВСЕХ ДРУГИХ КОМПОНЕНТОВ
    init_gate(app)

    # Инициализация компонентов приложения
    try:
        initialize_components(app)
    except SystemExit:
        raise
    except Exception as e:
        logger.critical(f"Критическая ошибка при инициализации компонентов: {e}")
        sys.exit(1)

    # Регистрация blueprint'ов
    register_blueprints(app)

    # Регистрация обработчиков ошибок
    register_error_handlers(app)

    logger.info("Приложение успешно инициализировано")
    return app


def initialize_components(app):
    """Инициализация компонентов приложения"""
    try:
        logger.info("Инициализация базы данных...")
        
        # Инициализируем БД (вся логика получения параметров внутри)
        initialize_database(app)

        # Проверяем, что БД действительно инициализирована
        if not is_database_initialized():
            logger.critical("База данных не инициализирована")
            sys.exit(1)

        logger.info("База данных успешно инициализирована")

    except SystemExit:
        raise
    except Exception as e:
        logger.critical(f"Ошибка инициализации базы данных: {e}")
        sys.exit(1)
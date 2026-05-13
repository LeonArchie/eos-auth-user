# maintenance/app_init.py
# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import sys
from flask import Flask

from handlers.gate import init_gate
from handlers.incoming_logger import IncomingRequestLogger
from handlers.outgoing_logger import OutgoingRequestLogger
from maintenance.logging_config import setup_logging
from maintenance.database_connector import initialize_database, is_database_initialized
from maintenance.app_blueprint import register_blueprints, register_error_handlers
from maintenance.configurations.get_env_config import get_env_config

logger = setup_logging()


def create_app():
    """Создание и инициализация Flask приложения"""
    app = Flask(__name__)

    # Настройка базы данных
    database_user = get_env_config('DATABASE_USER')
    database_password = get_env_config('DB_PASSWORD')
    database_host = get_env_config('DATABASE_HOST', default='localhost')
    database_port = get_env_config('DATABASE_PORT', default='5432')
    database_name = get_env_config('DATABASE_NAME', default='postgres')

    app.config['SQLALCHEMY_DATABASE_URI'] = (
        f"postgresql://{database_user}:{database_password}@"
        f"{database_host}:{database_port}/{database_name}"
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
    }

    # Инициализация логгеров
    incoming_logger = IncomingRequestLogger(app)
    outgoing_logger = OutgoingRequestLogger()

    app.config['INCOMING_LOGGER'] = incoming_logger
    app.config['OUTGOING_LOGGER'] = outgoing_logger

    # ИНИЦИАЛИЗАЦИЯ ШЛЮЗА
    init_gate(app)

    # Инициализация компонентов приложения
    try:
        initialize_components(app)
    except SystemExit:
        raise
    except Exception as e:
        logger.critical(f"Критическая ошибка при инициализации компонентов: {e}")
        sys.exit(1)

    register_blueprints(app)
    register_error_handlers(app)

    logger.info("Приложение успешно инициализировано")
    return app


def initialize_components(app):
    """Инициализация компонентов приложения"""
    try:
        logger.info("Инициализация базы данных...")
        initialize_database(app)

        if not is_database_initialized():
            logger.critical("База данных не инициализирована")
            sys.exit(1)

        logger.info("База данных успешно инициализирована")

    except SystemExit:
        raise
    except Exception as e:
        logger.critical(f"Ошибка инициализации базы данных: {e}")
        sys.exit(1)
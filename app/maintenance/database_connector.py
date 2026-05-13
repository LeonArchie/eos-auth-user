# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import logging
import time
from contextlib import contextmanager
from typing import Iterator
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from maintenance.configurations.get_global_config import get_global_config, SERVER_ERROR, DATA_ERROR
from maintenance.configurations.get_env_config import get_env_config

logger = logging.getLogger(__name__)

# Глобальный экземпляр SQLAlchemy
db = SQLAlchemy()


def _get_db_config_with_retry(param_path: str, max_retries: int = 10, retry_delay: float = 5.0) -> str:
    """
    Получение параметра конфигурации из глобального сервиса с повторными попытками.
    
    :param param_path: путь к параметру
    :param max_retries: максимальное количество попыток
    :param retry_delay: задержка между попытками в секундах
    :return: значение параметра
    :raises: RuntimeError если параметр не получен после всех попыток
    """
    for attempt in range(1, max_retries + 1):
        try:
            value = get_global_config(param_path)
            
            if value not in [SERVER_ERROR, DATA_ERROR]:
                logger.info(f"Параметр {param_path} успешно получен")
                return value
            else:
                logger.warning(f"Ошибка получения параметра {param_path} (попытка {attempt}/{max_retries})")
        except Exception as e:
            logger.warning(f"Исключение при получении параметра {param_path} (попытка {attempt}/{max_retries}): {str(e)}")
        
        if attempt < max_retries:
            logger.info(f"Повторная попытка получения параметра {param_path} через {retry_delay} сек")
            time.sleep(retry_delay)
    
    error_msg = f"Не удалось получить параметр {param_path} после {max_retries} попыток"
    logger.error(error_msg)
    raise RuntimeError(error_msg)


def _load_db_configuration() -> dict:
    """
    Загрузка конфигурации БД из глобального сервиса конфигураций и .env файла.
    
    :return: словарь с параметрами подключения к БД
    :raises: RuntimeError если не удалось загрузить конфигурацию
    """
    logger.info("Загрузка конфигурации БД из глобального сервиса конфигураций")
    
    # Параметры для получения из глобального сервиса
    config_params = {
        'master_host': 'db/master_host',
        'master_port': 'db/master_port',
        'database': 'db/database',
        'pool_size': 'db/pool_size',
        'max_overflow': 'db/max_overflow',
        'pool_timeout': 'db/pool_timeout',
        'pool_recycle': 'db/pool_recycle',
        'pool_pre_ping': 'db/pool_pre_ping',
        'max_retries': 'db/max_retries',
        'retry_delay': 'db/retry_delay'
    }
    
    config = {}
    for key, param_path in config_params.items():
        value = _get_db_config_with_retry(param_path)
        config[key] = value
        logger.info(f"Конфигурация {key}: {value}")
    
    # Загрузка учетных данных из .env
    database_user = get_env_config('DATABASE_USER')
    database_password = get_env_config('DB_PASSWORD')
    
    if not database_user:
        raise RuntimeError("DATABASE_USER не найден в .env файле")
    if not database_password:
        raise RuntimeError("DB_PASSWORD не найден в .env файле")
    
    config['user'] = database_user
    config['password'] = database_password
    
    logger.info("Учетные данные успешно загружены из .env")
    
    return config


class DatabaseConnector:
    """Класс для управления подключениями к базе данных через Flask-SQLAlchemy"""

    def __init__(self):
        self._initialized = False
        self._app = None
        logger.info("Инициализация DatabaseConnector")

    def initialize(self, app: Flask) -> None:
        """Инициализация подключения к базе данных"""
        if self._initialized:
            logger.debug("База данных уже инициализирована")
            return

        if not app:
            logger.error("Не передан объект Flask приложения для инициализации БД")
            raise RuntimeError("Flask приложение не передано для инициализации БД")

        try:
            # Загружаем конфигурацию БД
            db_config = _load_db_configuration()
            
            # Формируем строку подключения
            connection_string = (
                f"postgresql://{db_config['user']}:{db_config['password']}@"
                f"{db_config['master_host']}:{db_config['master_port']}/"
                f"{db_config['database']}"
            )
            
            # Настраиваем Flask-SQLAlchemy
            app.config['SQLALCHEMY_DATABASE_URI'] = connection_string
            app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
            
            # Обрабатываем pool_pre_ping - может быть строкой или булевым значением
            pool_pre_ping = db_config['pool_pre_ping']
            if isinstance(pool_pre_ping, bool):
                pool_pre_ping_value = pool_pre_ping
            elif isinstance(pool_pre_ping, str):
                pool_pre_ping_value = pool_pre_ping.lower() == 'true'
            else:
                pool_pre_ping_value = False
                logger.warning(f"Неизвестный тип pool_pre_ping: {type(pool_pre_ping)}, используется False")
            
            app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
                'pool_size': int(db_config['pool_size']),
                'max_overflow': int(db_config['max_overflow']),
                'pool_timeout': int(db_config['pool_timeout']),
                'pool_recycle': int(db_config['pool_recycle']),
                'pool_pre_ping': pool_pre_ping_value,
            }
            
            self._app = app
            db.init_app(app)

            with app.app_context():
                # Reflection существующих таблиц
                db.metadata.reflect(bind=db.engine)
                tables = list(db.metadata.tables.keys())
                if tables:
                    logger.info(f"Загружены таблицы через reflection: {tables}")
                else:
                    logger.warning("Не найдено таблиц в БД при reflection")

            self._initialized = True
            logger.info("База данных успешно инициализирована через Flask-SQLAlchemy")

        except Exception as e:
            logger.error(f"Ошибка инициализации БД: {str(e)}", exc_info=True)
            raise

    def is_healthy(self) -> bool:
        """Проверка работоспособности базы данных"""
        if not self._initialized:
            logger.warning("Попытка проверки здоровья неинициализированной БД")
            return False

        try:
            result = db.session.execute(db.text("SELECT 1")).scalar()
            return result == 1
        except Exception as e:
            logger.error(f"Ошибка при проверке здоровья БД: {str(e)}")
            return False

    @contextmanager
    def get_session(self) -> Iterator:
        """Контекстный менеджер для работы с сессией БД"""
        if not self._initialized:
            error_msg = "Попытка создать сессию неинициализированной БД"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        session_id = id(db.session)

        try:
            logger.debug(f"Открытие сессии БД (ID: {session_id})")
            yield db.session
            db.session.commit()
            logger.debug(f"Сессия БД успешно завершена (ID: {session_id})")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка в сессии {session_id}: {str(e)}", exc_info=True)
            raise

        finally:
            db.session.remove()
            logger.debug(f"Сессия БД закрыта (ID: {session_id})")

    def close(self) -> None:
        """Закрытие соединения с БД"""
        if not self._initialized:
            logger.debug("Попытка закрыть неинициализированное соединение")
            return

        logger.info("Закрытие соединения с БД")
        db.session.remove()
        if self._app:
            with self._app.app_context():
                db.engine.dispose()
        self._initialized = False

    def is_initialized(self) -> bool:
        """Проверка инициализации подключения к БД"""
        return self._initialized


# Глобальный экземпляр коннектора
_db_connector = None


def get_db_connector() -> DatabaseConnector:
    """Получение глобального экземпляра DatabaseConnector (синглтон)"""
    global _db_connector
    if _db_connector is None:
        logger.info("Создание нового экземпляра DatabaseConnector")
        _db_connector = DatabaseConnector()
    return _db_connector


def initialize_database(app: Flask) -> None:
    """Инициализация базы данных"""
    connector = get_db_connector()
    connector.initialize(app)


def close_database() -> None:
    """Закрытие подключения к базе данных"""
    connector = get_db_connector()
    connector.close()


def is_database_healthy() -> bool:
    """Проверка работоспособности базы данных"""
    connector = get_db_connector()
    return connector.is_healthy()


def is_database_initialized() -> bool:
    """Проверка инициализации базы данных"""
    connector = get_db_connector()
    return connector.is_initialized()
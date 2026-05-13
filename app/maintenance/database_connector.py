# maintenance/database_connector.py
# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import logging
from contextlib import contextmanager
from typing import Iterator
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)

# Глобальный экземпляр SQLAlchemy
db = SQLAlchemy()


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
            self._app = app
            db.init_app(app)

            with app.app_context():
                # Reflection существующих таблиц (для доступа через db.metadata.tables)
                db.metadata.reflect(bind=db.engine)

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
# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

"""
Управление флагами и их инициализация.
"""

import logging
from typing import Dict
from maintenance.configurations.get_env_config import init_env_check
from maintenance.configurations.get_local_config import init_local_config_check
from maintenance.configurations.get_global_config import init_global_config_check
from maintenance.flag_state import (
    get_flag_state, set_env_flag,
    set_local_flag, get_global_flag, set_global_flag,
    set_db_flag, register_flag_callback,
    set_migration_flag
)

logger = logging.getLogger(__name__)

def get_all_flags() -> Dict[str, int]:
    """Получение всех флагов"""
    return get_flag_state().get_all_flags()

def update_app_config_with_flags(app):
    """Обновление конфигурации Flask текущими значениями флагов"""
    flags = get_all_flags()
    for flag_name, flag_value in flags.items():
        app.config[flag_name] = flag_value

def init_all_flags():
    """Инициализация всех флагов при запуске"""
    # Проверка наличия .env файла
    env_exists = init_env_check()
    set_env_flag(env_exists)

    # Проверка наличия global.conf файла
    local_config_exists = init_local_config_check()
    set_local_flag(local_config_exists)

    # Проверка доступности глобального сервиса конфигураций
    global_available = init_global_config_check()
    set_global_flag(global_available)
    
    # Инициализация флага БД (будет установлен при успешной инициализации)
    set_db_flag(0)
    
    # Инициализация флага миграций (будет установлен при выполнении миграций)
    set_migration_flag(0)
    
    # Регистрируем callback для синхронизации с Flask приложением
    register_flag_callback('FLAG_GET_GLOBAL', lambda name, old, new: sync_global_flag_to_flask())
    register_flag_callback('FLAG_DB_ACTIVE', lambda name, old, new: sync_db_flag_to_flask())
    register_flag_callback('FLAG_MIGRATION_COMPLETE', lambda name, old, new: sync_migration_flag_to_flask())

def sync_migration_flag_to_flask():
    """Синхронизация флага миграций с Flask приложением"""
    try:
        from flask import current_app
        if current_app:
            from maintenance.flag_state import get_migration_flag
            current_app.config['FLAG_MIGRATION_COMPLETE'] = get_migration_flag()
    except RuntimeError:
        pass

def sync_global_flag_to_flask():
    """Синхронизация глобального флага с Flask приложением"""
    try:
        from flask import current_app
        if current_app:
            current_app.config['FLAG_GET_GLOBAL'] = get_global_flag()
    except RuntimeError:
        pass

def sync_db_flag_to_flask():
    """Синхронизация флага БД с Flask приложением"""
    try:
        from flask import current_app
        if current_app:
            from maintenance.flag_state import get_db_flag
            current_app.config['FLAG_DB_ACTIVE'] = get_db_flag()
    except RuntimeError:
        pass
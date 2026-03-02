# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

"""
Централизованное хранение состояния флагов без зависимостей от других модулей.
"""

import threading
from typing import Dict, Callable
from enum import IntEnum

class FlagStatus(IntEnum):
    """Статусы для флагов"""
    DISABLED = 0
    ENABLED = 1
    ERROR = -1
    UNKNOWN = -2

class FlagState:
    """
    Синглтон для хранения состояния флагов.
    Не имеет зависимостей от других модулей.
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        with self._lock:
            if not self._initialized:
                self._flags = {
                    'FLAG_GET_ENV': FlagStatus.UNKNOWN, # Инициализировано считывание env секретов
                    'FLAG_GET_LOCAL': FlagStatus.UNKNOWN, # Инициализировано считывание global конфигураций
                    'FLAG_GET_GLOBAL': FlagStatus.UNKNOWN, # Инициализировано считывание внешних секретов
                    'FLAG_DB_ACTIVE': FlagStatus.UNKNOWN, # Инициализирована база данных
                    'FLAG_MIGRATION_COMPLETE': FlagStatus.UNKNOWN, # Статус миграций (0=ошибка, 1=успех, 2=выполняется)
                }
                self._callbacks = {}
                self._initialized = True
    
    def get_flag(self, flag_name: str) -> int:
        with self._lock:
            return self._flags.get(flag_name, FlagStatus.UNKNOWN)
    
    def set_flag(self, flag_name: str, value: int) -> bool:
        with self._lock:
            if flag_name not in self._flags:
                return False
            
            old_value = self._flags[flag_name]
            if old_value != value:
                self._flags[flag_name] = value
                
                if flag_name in self._callbacks:
                    for callback in self._callbacks[flag_name]:
                        try:
                            callback(flag_name, old_value, value)
                        except Exception:
                            pass
            return True
    
    def register_callback(self, flag_name: str, callback):
        with self._lock:
            if flag_name not in self._callbacks:
                self._callbacks[flag_name] = []
            self._callbacks[flag_name].append(callback)
    
    def get_all_flags(self) -> Dict[str, int]:
        with self._lock:
            return self._flags.copy()

# Глобальный экземпляр
_flag_state = None

def get_flag_state() -> FlagState:
    global _flag_state
    if _flag_state is None:
        _flag_state = FlagState()
    return _flag_state

# Простые функции доступа
def get_env_flag() -> int:
    return get_flag_state().get_flag('FLAG_GET_ENV')

def set_env_flag(value: int):
    get_flag_state().set_flag('FLAG_GET_ENV', value)

def get_local_flag() -> int:
    return get_flag_state().get_flag('FLAG_GET_LOCAL')

def set_local_flag(value: int):
    get_flag_state().set_flag('FLAG_GET_LOCAL', value)

def get_global_flag() -> int:
    return get_flag_state().get_flag('FLAG_GET_GLOBAL')

def set_global_flag(value: int):
    get_flag_state().set_flag('FLAG_GET_GLOBAL', value)

def get_db_flag() -> int:
    return get_flag_state().get_flag('FLAG_DB_ACTIVE')

def set_db_flag(value: int):
    get_flag_state().set_flag('FLAG_DB_ACTIVE', value)
    
def get_migration_flag() -> int:
    return get_flag_state().get_flag('FLAG_MIGRATION_COMPLETE')

def set_migration_flag(value: int):
    get_flag_state().set_flag('FLAG_MIGRATION_COMPLETE', value)

def register_flag_callback(flag_name: str, callback: Callable):
    """
    Регистрирует callback для отслеживания изменений флага
    """
    get_flag_state().register_callback(flag_name, callback)
# maintenance/configurations/get_local_config.py
# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from maintenance.flag_state import get_local_flag, set_local_flag

# Кэш для хранения параметров из global.conf
_CONFIG_CACHE: Dict[str, str] = {}

# Инициализируем логгер
logger = logging.getLogger(__name__)


def check_local_config_exists() -> int:
    """
    Проверка существования global.conf файла в корне приложения
    и загрузка его в кэш
    
    Returns:
        int: 1 если файл существует, иначе завершает программу с кодом 2
    """
    global _CONFIG_CACHE
    
    # Определяем путь к корню приложения
    root_dir = Path(__file__).parent.parent.parent
    config_path = root_dir / 'global.conf'
    
    if config_path.exists():
        set_local_flag(1)
        logger.debug("Файл global.conf найден, загрузка в кэш")
        
        # Загружаем файл в кэш
        try:
            with open(config_path, 'r', encoding='utf-8') as config_file:
                for line in config_file:
                    line = line.strip()
                    
                    if not line or line.startswith('#'):
                        continue
                    
                    if '=' in line:
                        name, value = line.split('=', 1)
                        name = name.strip()
                        value = value.strip().strip('\'"')
                        _CONFIG_CACHE[name] = value
                        
            logger.debug(f"Загружено {len(_CONFIG_CACHE)} параметров в кэш из global.conf")
            return 1
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке global.conf в кэш: {e}")
            set_local_flag(0)
            sys.exit(2)
    else:
        set_local_flag(0)
        logger.error("Файл global.conf не найден")
        sys.exit(2)


def get_local_config(param_name: str) -> Optional[str]:
    """
    Получение значения параметра из global.conf файла
    
    Args:
        param_name (str): Имя параметра для поиска в global.conf
        
    Returns:
        str or None: Значение параметра или None если параметр не найден
    """
    global _CONFIG_CACHE
    
    # Проверяем существование global.conf файла если флаг еще не установлен
    if get_local_flag() == 0:
        check_local_config_exists()
    
    # Если global.conf файл не существует, возвращаем None
    if get_local_flag() == 0:
        return None
    
    # Проверяем наличие параметра в кэше
    if param_name in _CONFIG_CACHE:
        value = _CONFIG_CACHE[param_name]
        logger.debug(f"Передан параметр {param_name}:{value} (из кэша)")
        return value
    
    try:
        # Если параметра нет в кэше, ищем в файле
        root_dir = Path(__file__).parent.parent.parent
        config_path = root_dir / 'global.conf'
        
        with open(config_path, 'r', encoding='utf-8') as config_file:
            for line in config_file:
                line = line.strip()
                
                if not line or line.startswith('#'):
                    continue
                
                if '=' in line:
                    name, value = line.split('=', 1)
                    name = name.strip()
                    
                    if name == param_name:
                        value = value.strip().strip('\'"')
                        
                        # Добавляем в кэш
                        _CONFIG_CACHE[param_name] = value
                        
                        logger.debug(f"Передан параметр {param_name}:{value} (из файла)")
                        return value
        
        # Параметр не найден
        logger.warning(f"Параметр {param_name} - не найден")
        return None
        
    except Exception as e:
        logger.error(f"Ошибка при чтении global.conf файла: {e}")
        return None


def init_local_config_check() -> int:
    """
    Инициализация проверки global.conf файла при запуске приложения
    
    Returns:
        int: 1 если файл существует, иначе завершает программу с кодом 2
    """
    return check_local_config_exists()


def get_cache_stats() -> Dict[str, Any]:
    """
    Получение статистики кэша (для отладки)
    
    Returns:
        Dict: Статистика кэша
    """
    return {
        'cache_size': len(_CONFIG_CACHE),
        'cache_keys': list(_CONFIG_CACHE.keys()),
        'flag_get_local': get_local_flag()
    }


def clear_cache():
    """Очистка кэша (для тестирования)"""
    global _CONFIG_CACHE
    _CONFIG_CACHE = {}
    logger.debug("Кэш global.conf очищен")  
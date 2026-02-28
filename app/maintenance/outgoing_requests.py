# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import logging
from pathlib import Path
from typing import Optional
from functools import wraps
import requests

# Настройка логгера с именем модуля
logger = logging.getLogger(__name__)

# Глобальная переменная для хранения MODULE_ID
_module_id: Optional[str] = None

def _load_module_id_from_config() -> str:
    """
    Загружает MODULE_ID из файла global.conf
    
    Returns:
        str: Значение MODULE_ID или пустая строка в случае ошибки
    """
    # Определяем путь к global.conf
    current_dir = Path(__file__).parent.parent
    config_file_path = current_dir / 'global.conf'
    
    logger.debug(f"Поиск конфигурационного файла: {config_file_path}")
    
    if not config_file_path.exists():
        logger.error(f"Файл конфигурации не найден: {config_file_path}")
        return ""
    
    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Пропускаем пустые строки и комментарии
                if not line or line.startswith('#'):
                    continue
                    
                if line.startswith('MODULE_ID='):
                    module_id = line.split('=', 1)[1].strip()
                    
                    if module_id:
                        logger.info(f"MODULE_ID успешно загружен из файла {config_file_path.name}")
                        logger.debug(f"Значение MODULE_ID: {module_id[:3]}...{module_id[-3:] if len(module_id) > 6 else module_id}")
                        return module_id
                    else:
                        logger.warning(f"Найдена пустая строка MODULE_ID в строке {line_num}")
        
        logger.warning(f"Параметр MODULE_ID не найден в файле {config_file_path.name}")
        return ""
        
    except PermissionError as e:
        logger.error(f"Нет прав на чтение файла конфигурации: {e}")
        return ""
    except UnicodeDecodeError as e:
        logger.error(f"Ошибка кодировки файла конфигурации: {e}")
        return ""
    except Exception as e:
        logger.error(f"Неожиданная ошибка при загрузке MODULE_ID: {e}", exc_info=True)
        return ""

def get_module_id() -> str:
    """
    Получение MODULE_ID с ленивой загрузкой
    
    Returns:
        str: Значение MODULE_ID или пустая строка
    """
    global _module_id
    
    if _module_id is None:
        logger.debug("Инициализация MODULE_ID (первый вызов)")
        _module_id = _load_module_id_from_config()
        
        if _module_id:
            logger.info(f"MODULE_ID инициализирован: длина={len(_module_id)}")
        else:
            logger.warning("MODULE_ID не инициализирован (пустое значение)")
    
    return _module_id

def inject_module_id_to_requests():
    """
    Модифицирует стандартные функции requests для автоматического добавления MODULE-ID
    """
    logger.debug("Запуск процедуры инъекции MODULE-ID в requests")
    
    module_id = get_module_id()
    
    if not module_id:
        logger.warning("MODULE-ID не найден, инъекция заголовка не выполнена")
        return
    
    try:
        original_request = requests.Session.request
        
        @wraps(original_request)
        def wrapped_request(session, method, url, **kwargs):
            # Добавляем MODULE-ID к заголовкам
            headers = kwargs.get('headers', {}).copy()  # Создаем копию чтобы не изменять оригинал
            headers['MODULE-ID'] = module_id
            kwargs['headers'] = headers
            
            # Логируем информацию о запросе (без чувствительных данных)
            logger.debug(f"Добавлен заголовок MODULE-ID к запросу: {method} {url.split('?')[0]}")
            
            return original_request(session, method, url, **kwargs)
        
        # Заменяем метод request в Session
        requests.Session.request = wrapped_request
        logger.info(f"Глобальная инъекция MODULE-ID успешно выполнена. MODULE-ID: {module_id[:3]}...{module_id[-3:] if len(module_id) > 6 else module_id}")
        
    except AttributeError as e:
        logger.error(f"Ошибка доступа к методу requests.Session.request: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при инъекции MODULE-ID: {e}", exc_info=True)

# Автоматически выполняем инъекцию при импорте модуля
logger.debug("Модуль outgoing_requests загружается, запуск автоматической инъекции")
inject_module_id_to_requests()
logger.debug("Завершение загрузки модуля outgoing_requests")
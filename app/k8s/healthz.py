# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

# Импорт необходимых модулей
from flask import Blueprint, jsonify
import logging

# Импорт для получения флагов
from maintenance.flag_state import get_env_flag, get_local_flag, get_global_flag

# Создаем логгер для текущего модуля
logger = logging.getLogger(__name__)

# Создаем Blueprint для healthcheck-эндпоинтов
healthz_bp = Blueprint('healthz', __name__)

def _check_critical_flags():
    """
    Проверка критических флагов для liveness пробы:
    - FLAG_GET_ENV: наличие .env файла
    - FLAG_GET_LOCAL: наличие global.conf файла
    - FLAG_GET_GLOBAL: доступность глобального сервиса конфигураций
    
    Returns:
        tuple: (успех, список проблем)
    """
    issues = []
    
    # Проверяем флаг FLAG_GET_ENV
    env_flag = get_env_flag()
    if env_flag != 1:
        issues.append(f"FLAG_GET_ENV={env_flag} (ожидается 1)")
        logger.warning(f"FLAG_GET_ENV = {env_flag} (ожидается 1)")
    
    # Проверяем флаг FLAG_GET_LOCAL
    local_flag = get_local_flag()
    if local_flag != 1:
        issues.append(f"FLAG_GET_LOCAL={local_flag} (ожидается 1)")
        logger.warning(f"FLAG_GET_LOCAL = {local_flag} (ожидается 1)")
    
    # Проверяем флаг FLAG_GET_GLOBAL
    global_flag = get_global_flag()
    if global_flag != 1:
        issues.append(f"FLAG_GET_GLOBAL={global_flag} (ожидается 1)")
        logger.warning(f"FLAG_GET_GLOBAL = {global_flag} (ожидается 1)")
    
    return len(issues) == 0, issues

# Декорируем функцию для обработки GET-запросов по пути '/healthz'
@healthz_bp.route('/healthz', methods=['GET'])
def healthz():
    """
    Liveness проба для Kubernetes.
    Проверяет, что сервис жив и может функционировать.
    
    Возвращает:
        200 OK: если все критические флаги установлены в 1
        503 Service Unavailable: если хотя бы один критический флаг не равен 1
    """
    logger.debug("Проверка liveness (живости) сервиса")
    
    # Проверяем критические флаги
    all_flags_ok, issues = _check_critical_flags()
    
    # Формируем ответ
    if all_flags_ok:
        response_data = {
            "status": True,
            "message": "Service is alive",
            "flags": {
                "FLAG_GET_ENV": get_env_flag(),
                "FLAG_GET_LOCAL": get_local_flag(),
                "FLAG_GET_GLOBAL": get_global_flag()
            }
        }
        logger.debug("Liveness проверка успешна: все критические флаги = 1")
        return jsonify(response_data), 200
    else:
        response_data = {
            "status": False,
            "message": "Service is not alive",
            "issues": issues,
            "flags": {
                "FLAG_GET_ENV": get_env_flag(),
                "FLAG_GET_LOCAL": get_local_flag(),
                "FLAG_GET_GLOBAL": get_global_flag()
            }
        }
        logger.warning(f"Liveness проверка не пройдена: {', '.join(issues)}")
        return jsonify(response_data), 503  # Service Unavailable

# Примечания:
# 1. Этот эндпоинт проверяет "живость" сервиса (liveness probe)
# 2. Kubernetes перезапускает контейнер если /healthz возвращает ошибку
# 3. Проверки должны быть легковесными и быстрыми
# 4. Критические флаги: 
#    - FLAG_GET_ENV = 1: .env файл существует
#    - FLAG_GET_LOCAL = 1: global.conf файл существует
#    - FLAG_GET_GLOBAL = 1: сервис глобальных конфигураций доступен
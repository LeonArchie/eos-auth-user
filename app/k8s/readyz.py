# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

from flask import Blueprint, jsonify
import logging

# Импорт для получения флагов
from maintenance.flag_state import (
    get_env_flag, get_local_flag, get_global_flag,
    get_db_flag, get_migration_flag
)

logger = logging.getLogger(__name__)
readyz_bp = Blueprint('readyz', __name__)

def _check_all_flags():
    """
    Проверка всех флагов для readiness пробы:
    - FLAG_GET_ENV: наличие .env файла
    - FLAG_GET_LOCAL: наличие global.conf файла
    - FLAG_GET_GLOBAL: доступность глобального сервиса конфигураций
    - FLAG_DB_ACTIVE: активность базы данных
    - FLAG_MIGRATION_COMPLETE: статус миграций (1 - успешно, 2 - выполняется)
    
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
    
    # Проверяем флаг FLAG_DB_ACTIVE
    db_flag = get_db_flag()
    if db_flag != 1:
        issues.append(f"FLAG_DB_ACTIVE={db_flag} (ожидается 1)")
        logger.warning(f"FLAG_DB_ACTIVE = {db_flag} (ожидается 1)")
    
    # Проверяем флаг FLAG_MIGRATION_COMPLETE
    migration_flag = get_migration_flag()
    if migration_flag not in [1, 2]:
        issues.append(f"FLAG_MIGRATION_COMPLETE={migration_flag} (ожидается 1 или 2)")
        logger.warning(f"FLAG_MIGRATION_COMPLETE = {migration_flag} (ожидается 1 или 2)")
    elif migration_flag == 2:
        logger.info("Миграции выполняются (FLAG_MIGRATION_COMPLETE=2) - сервис считается готовым")
    
    return len(issues) == 0, issues

@readyz_bp.route('/readyz', methods=['GET'])
def readyz():
    """
    Readiness проба для Kubernetes.
    Проверяет, что сервис готов принимать трафик.
    
    Возвращает:
        200 OK: если все необходимые флаги установлены корректно
        503 Service Unavailable: если хотя бы один необходимый флаг не в нужном состоянии
    """
    logger.debug("Проверка readiness (готовности) сервиса")
    
    # Проверяем все флаги
    all_flags_ok, issues = _check_all_flags()
    
    # Получаем текущие значения флагов
    flags = {
        "FLAG_GET_ENV": get_env_flag(),
        "FLAG_GET_LOCAL": get_local_flag(),
        "FLAG_GET_GLOBAL": get_global_flag(),
        "FLAG_DB_ACTIVE": get_db_flag(),
        "FLAG_MIGRATION_COMPLETE": get_migration_flag()
    }
    
    # Формируем ответ
    if all_flags_ok:
        response_data = {
            "status": True,
            "message": "Service is ready to accept traffic",
            "flags": flags,
            "migration_status": "in_progress" if flags["FLAG_MIGRATION_COMPLETE"] == 2 else "complete"
        }
        
        if flags["FLAG_MIGRATION_COMPLETE"] == 2:
            logger.debug("Readiness проверка успешна: миграции выполняются, сервис готов")
        else:
            logger.debug("Readiness проверка успешна: все флаги = 1")
            
        return jsonify(response_data), 200
    else:
        response_data = {
            "status": False,
            "message": "Service is not ready to accept traffic",
            "issues": issues,
            "flags": flags
        }
        logger.warning(f"Readiness проверка не пройдена: {', '.join(issues)}")
        return jsonify(response_data), 503  # Service Unavailable

# Основные принципы работы этого endpoint:
#
# 1. Отличие от /healthz:
#    - /healthz проверяет "живость" сервиса (liveness) - критически важные компоненты
#    - /readyz проверяет готовность обрабатывать запросы (readiness) - все необходимые компоненты
#
# 2. Типичные сценарии использования:
#    - Kubernetes использует для управления подами трафика
#    - Балансировщики нагрузки для исключения/включения нод
#    - В оркестраторах при rolling updates
#
# 3. Проверяемые компоненты:
#    - FLAG_GET_ENV: наличие .env файла (критично)
#    - FLAG_GET_LOCAL: наличие global.conf файла (критично)
#    - FLAG_GET_GLOBAL: доступность глобального сервиса конфигураций (критично)
#    - FLAG_DB_ACTIVE: активность базы данных (критично)
#    - FLAG_MIGRATION_COMPLETE: статус миграций (1 - успешно, 2 - выполняется)
#
# 4. Особенности проверки миграций:
#    - FLAG_MIGRATION_COMPLETE = 1: миграции успешно завершены
#    - FLAG_MIGRATION_COMPLETE = 2: миграции выполняются (сервис считается готовым)
#    - FLAG_MIGRATION_COMPLETE = 0: ошибка миграций (сервис не готов)
#
# 5. Оптимизации:
#    - Минимизировать внешние зависимости проверок
#    - Использовать флаги вместо прямых проверок для скорости
#    - Добавлять timeout для внешних проверок
#
# 6. Безопасность:
#    - Не раскрывает sensitive-информацию
#    - Рекомендуется закрыть от публичного доступа
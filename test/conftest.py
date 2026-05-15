# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import pytest
import sys
import uuid
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

# Добавляем путь к app в PYTHONPATH
APP_DIR = Path(__file__).parent.parent / 'app'
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


# ============================================================
# ТЕСТОВЫЕ КОНФИГУРАЦИИ
# ============================================================

TEST_CONFIG = {
    'DB_ENABLE': 'false',
    'MASTER_HOST': 'localhost',
    'MASTER_PORT': '5432',
    'DB_NAME': 'test_db',
    'DB_POOL_SIZE': '5',
    'DB_MAX_OVERFLOW': '10',
    'DB_POOL_TIMEOUT': '60',
    'DB_POOL_RECYCLE': '3600',
    'DB_POOL_PRE_PING': 'true',
    'DB_MAX_RETRIES': '5',
    'RETRY_DELAY': '5',
    'NAME_APP': 'Test-App',
    'LOG_LVL': 'DEBUG',
    'MODULE_ID': 'TEST-MODULE',
    'URL_CONFIG_MODULES': 'http://test-config-service:9443',
    'URL_AUDIT_MODULES': 'http://test-audit-service:9443',
    'URL_AUTH_USER_MODULES': 'http://test-auth-service:9443',
}


# ============================================================
# ТЕСТОВЫЕ ПРАВИЛА ДЛЯ GATE
# ============================================================

TEST_GATE_RULES = [
    {
        'name': 'test-ok',
        'path': '^/test/ok$',
        'method': 'GET',
        'headers': [],
        'body': {},
        'rqid': False
    },
    {
        'name': 'test-secure',
        'path': '^/test/secure$',
        'method': 'POST',
        'headers': [
            {'name': 'module-id', 'value': 'TEST-MODULE', 'name_lower': 'module-id'}
        ],
        'body': {
            'username': '^[a-zA-Z0-9_]{3,20}$',
            'password': '^.{6,100}$'
        },
        'rqid': True
    },
    {
        'name': 'test-login',
        'path': '^/v1/auth/login$',
        'method': 'POST',
        'headers': [
            {'name': 'module-id', 'value': 'TEST-CONF', 'name_lower': 'module-id'},
            {'name': 'module-id', 'value': 'TEST-BBEL', 'name_lower': 'module-id'}
        ],
        'body': {
            'login': '^[a-zA-Z0-9_.@-]+$',
            'password': '^.{6,100}$',
            'type': '^(internal|LDAP)$'
        },
        'rqid': True
    },
    {
        'name': 'healthz',
        'path': '^/healthz$',
        'method': 'GET',
        'headers': [],
        'body': {},
        'rqid': False
    },
    {
        'name': 'readyz',
        'path': '^/readyz$',
        'method': 'GET',
        'headers': [],
        'body': {},
        'rqid': False
    },
]


# ============================================================
# МОКИ ДЛЯ КОНФИГУРАЦИЙ
# ============================================================

def mock_get_local_config(param_name: str, default=None):
    """Мок для get_local_config - возвращает тестовые значения"""
    return TEST_CONFIG.get(param_name, default)


def mock_load_schemas():
    """Мок для load_schemas - возвращает тестовые правила gate"""
    import copy
    return copy.deepcopy(TEST_GATE_RULES)


# ============================================================
# ГЛОБАЛЬНЫЙ МОК (ТОЛЬКО ОДИН РАЗ!)
# ============================================================

@pytest.fixture(autouse=True, scope="session")
def mock_all_configurations():
    """Глобальный мок для всех конфигураций (выполняется один раз для всех тестов)"""
    
    # Патчим get_local_config во всех модулях
    patches = [
        patch('maintenance.configurations.get_local_config.get_local_config', 
              side_effect=mock_get_local_config),
        patch('maintenance.database_connector.get_local_config', 
              side_effect=mock_get_local_config),
        patch('maintenance.configurations.get_global_config.get_local_config',
              side_effect=mock_get_local_config),
        patch('maintenance.configurations.get_local_config.check_local_config_exists', 
              return_value=True),
        patch('maintenance.configurations.get_env_config.check_env_file_exists', 
              return_value=True),
        patch('maintenance.configurations.get_env_config.get_env_config',
              side_effect=lambda name, default=None: {
                  'DATABASE_USER': 'test_user',
                  'DB_PASSWORD': 'test_password'
              }.get(name, default)),
    ]
    
    for p in patches:
        p.start()
    
    # Отключаем БД
    patch('maintenance.database_connector.is_db_enabled', return_value=False).start()
    patch('maintenance.database_connector.is_database_enabled', return_value=False).start()
    patch('maintenance.database_connector.initialize_database').start()
    patch('maintenance.database_connector.is_database_initialized', return_value=True).start()
    patch('maintenance.database_connector.is_database_healthy', return_value=True).start()
    
    # Мокаем проверки healthz/readyz
    patch('k8s.healthz.check_global_config_available', return_value=True).start()
    patch('k8s.healthz.check_env_file_exists', return_value=True).start()
    patch('k8s.healthz.check_local_config_exists', return_value=True).start()
    
    patch('k8s.readyz.check_global_config_available', return_value=True).start()
    patch('k8s.readyz.check_env_file_exists', return_value=True).start()
    patch('k8s.readyz.check_local_config_exists', return_value=True).start()
    
    # Мокаем gate схемы
    patch('handlers.gate.load_schemas', side_effect=mock_load_schemas).start()
    
    yield


# ============================================================
# ФИКСТУРА ДЛЯ ОЧИСТКИ КЭШЕЙ
# ============================================================

@pytest.fixture(autouse=True)
def clear_caches():
    """Очищает все кэши перед каждым тестом"""
    try:
        from maintenance.configurations.get_local_config import clear_cache
        clear_cache()
    except ImportError:
        pass
    
    try:
        from maintenance.configurations.get_global_config import clear_config_cache
        clear_config_cache()
    except ImportError:
        pass
    
    # Сбрасываем кэш gate
    try:
        import handlers.gate as gate_module
        gate_module._schemas_cache = None
        gate_module._compiled_patterns_cache = {}
        gate_module._gate_healthy = True
        gate_module._gate_init_error = None
    except ImportError:
        pass
    
    yield


# ============================================================
# ФИКСТУРА ДЛЯ ВРЕМЕННОЙ ДИРЕКТОРИИ
# ============================================================

@pytest.fixture(scope="session")
def temp_project_dir():
    """Создает временную директорию с тестовыми конфигурациями"""
    temp_dir = tempfile.mkdtemp()
    
    # Копируем тестовые конфиги из fixtures
    fixtures_dir = Path(__file__).parent / 'fixtures'
    
    config_files = {
        "test_global.conf": "global.conf",
        "test_schemas.yaml": "schemas.yaml",
        "test.env": ".env"
    }
    
    for src_name, dest_name in config_files.items():
        src = fixtures_dir / src_name
        if src.exists():
            dest = Path(temp_dir) / dest_name
            shutil.copy(src, dest)
    
    return temp_dir


# ============================================================
# ТЕСТОВЫЕ ЭНДПОИНТЫ
# ============================================================

@pytest.fixture(autouse=True)
def register_test_endpoints(app):
    """Регистрирует тестовые эндпоинты для API тестов"""
    
    @app.route('/test/ok', methods=['GET'])
    def test_ok_endpoint():
        return {"status": "ok"}, 200
    
    @app.route('/test/secure', methods=['POST'])
    def test_secure_endpoint():
        return {"status": "secure"}, 200
    
    @app.route('/v1/auth/login', methods=['POST'])
    def test_login_endpoint():
        return {"status": "login"}, 200
    
    return app


# ============================================================
# ОСНОВНЫЕ ФИКСТУРЫ ДЛЯ ТЕСТОВ
# ============================================================

@pytest.fixture
def app(temp_project_dir, monkeypatch):
    """Создает тестовое Flask приложение"""
    monkeypatch.chdir(temp_project_dir)
    monkeypatch.syspath_prepend(str(APP_DIR))
    
    from maintenance.app_init import create_app
    app = create_app()
    app.config['TESTING'] = True
    
    return app


@pytest.fixture
def client(app):
    """Тестовый клиент Flask"""
    return app.test_client()


@pytest.fixture
def generate_rqid():
    """Генерирует UUID для Rqid заголовка"""
    return str(uuid.uuid4())


@pytest.fixture
def auth_headers(generate_rqid):
    """Заголовки для авторизованных запросов"""
    return {
        'MODULE-ID': 'TEST-CONF',
        'Rqid': generate_rqid
    }


@pytest.fixture
def valid_login_data():
    """Валидные данные для логина"""
    return {
        'login': 'testuser@example.com',
        'password': 'securepassword123',
        'type': 'internal'
    }


@pytest.fixture
def capture_logs(caplog):
    """Фикстура для захвата логов"""
    caplog.set_level("DEBUG")
    return caplog


@pytest.fixture
def reset_audit_module():
    """Сбрасывает состояние модуля аудита"""
    try:
        import handlers.audit as audit_module
        audit_module._module_name = None
        audit_module._audit_url = None
        audit_module._logger = None
    except (ImportError, AttributeError):
        pass
    yield
    try:
        import handlers.audit as audit_module
        audit_module._module_name = None
        audit_module._audit_url = None
        audit_module._logger = None
    except (ImportError, AttributeError):
        pass
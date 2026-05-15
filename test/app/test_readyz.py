# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import pytest


pytestmark = pytest.mark.unit


class TestReadyz:
    """Тесты для readyz эндпоинта"""
    
    def test_readyz_returns_200(self, client):
        """Тест успешного readyz запроса"""
        response = client.get('/readyz')
        assert response.status_code == 200
    
    def test_readyz_response_structure(self, client):
        """Тест структуры ответа readyz"""
        response = client.get('/readyz')
        data = response.get_json()
        
        assert data['status'] is True
        assert data['message'] == 'Service is ready to accept traffic'
        assert 'checks' in data
    
    def test_readyz_contains_database_checks(self, client):
        """Тест наличия проверок БД в ответе"""
        response = client.get('/readyz')
        data = response.get_json()
        
        assert 'database_enabled' in data['checks']
        assert 'database_initialized' in data['checks']
        assert 'database_healthy' in data['checks']
    
    def test_readyz_only_get_allowed(self, client):
        """Тест что только GET метод разрешен"""
        response = client.post('/readyz')
        assert response.status_code == 403
    
    def test_readyz_returns_json(self, client):
        """Тест что readyz возвращает JSON"""
        response = client.get('/readyz')
        assert response.content_type == 'application/json'
    
    def test_readyz_response_time(self, client):
        """Тест времени ответа readyz"""
        import time
        
        start = time.time()
        response = client.get('/readyz')
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 1.0
    
    def test_readyz_database_disabled(self, client, temp_project_dir, monkeypatch):
        """Тест когда БД отключена в конфигурации"""
        monkeypatch.chdir(temp_project_dir)
        
        # В тестовой конфигурации DB_ENABLE=false
        response = client.get('/readyz')
        data = response.get_json()
        
        assert data['checks']['database_enabled'] is False
        assert data['checks']['database_initialized'] is None
        assert data['checks']['database_healthy'] is None


class TestReadyzWithMocks:
    """Тесты readyz с моками"""
    
    def test_readyz_when_database_healthy(self, client, mocker):
        """Тест когда БД здорова"""
        mocker.patch('k8s.readyz.is_database_enabled', return_value=True)
        mocker.patch('k8s.readyz.is_database_initialized', return_value=True)
        mocker.patch('k8s.readyz.is_database_healthy', return_value=True)
        mocker.patch('k8s.readyz.check_env_file_exists', return_value=True)
        mocker.patch('k8s.readyz.check_local_config_exists', return_value=True)
        mocker.patch('k8s.readyz.check_global_config_available', return_value=True)
        
        response = client.get('/readyz')
        assert response.status_code == 200
    
    def test_readyz_when_database_unhealthy(self, client, mocker):
        """Тест когда БД нездорова"""
        mocker.patch('k8s.readyz.is_database_enabled', return_value=True)
        mocker.patch('k8s.readyz.is_database_initialized', return_value=True)
        mocker.patch('k8s.readyz.is_database_healthy', return_value=False)
        mocker.patch('k8s.readyz.check_env_file_exists', return_value=True)
        mocker.patch('k8s.readyz.check_local_config_exists', return_value=True)
        mocker.patch('k8s.readyz.check_global_config_available', return_value=True)
        
        response = client.get('/readyz')
        assert response.status_code == 503
        
        data = response.get_json()
        assert data['status'] is False
        assert 'База данных нездорова' in str(data['issues'])
    
    def test_readyz_when_database_not_initialized(self, client, mocker):
        """Тест когда БД не инициализирована"""
        mocker.patch('k8s.readyz.is_database_enabled', return_value=True)
        mocker.patch('k8s.readyz.is_database_initialized', return_value=False)
        mocker.patch('k8s.readyz.is_database_healthy', return_value=False)
        mocker.patch('k8s.readyz.check_env_file_exists', return_value=True)
        mocker.patch('k8s.readyz.check_local_config_exists', return_value=True)
        mocker.patch('k8s.readyz.check_global_config_available', return_value=True)
        
        response = client.get('/readyz')
        assert response.status_code == 503
        
        data = response.get_json()
        assert 'База данных не инициализирована' in str(data['issues'])
    
    def test_readyz_when_config_files_missing(self, client, mocker):
        """Тест когда конфигурационные файлы отсутствуют"""
        mocker.patch('k8s.readyz.is_database_enabled', return_value=False)
        mocker.patch('k8s.readyz.check_env_file_exists', return_value=False)
        mocker.patch('k8s.readyz.check_local_config_exists', return_value=False)
        mocker.patch('k8s.readyz.check_global_config_available', return_value=False)
        
        response = client.get('/readyz')
        assert response.status_code == 503
        
        data = response.get_json()
        assert data['status'] is False
        assert len(data['issues']) >= 3
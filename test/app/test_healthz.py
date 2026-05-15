# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import pytest


pytestmark = pytest.mark.unit


class TestHealthz:
    """Тесты для healthz эндпоинта"""
    
    def test_healthz_returns_200(self, client):
        """Тест успешного healthz запроса"""
        response = client.get('/healthz')
        assert response.status_code == 200
    
    def test_healthz_response_structure(self, client):
        """Тест структуры ответа healthz"""
        response = client.get('/healthz')
        data = response.get_json()
        
        assert 'status' in data
        assert 'message' in data
        assert 'checks' in data
        assert data['status'] is True
    
    def test_healthz_contains_all_checks(self, client):
        """Тест наличия всех необходимых проверок"""
        response = client.get('/healthz')
        data = response.get_json()
        
        expected_checks = ['env_file', 'local_config', 'global_config']
        for check in expected_checks:
            assert check in data['checks']
    
    def test_healthz_only_get_allowed(self, client):
        """Тест что только GET метод разрешен"""
        response = client.post('/healthz')
        assert response.status_code == 403
        
        response = client.put('/healthz')
        assert response.status_code == 403
        
        response = client.delete('/healthz')
        assert response.status_code == 403
    
    def test_healthz_returns_json(self, client):
        """Тест что healthz возвращает JSON"""
        response = client.get('/healthz')
        assert response.content_type == 'application/json'
    
    def test_healthz_response_time(self, client):
        """Тест времени ответа healthz"""
        import time
        
        start = time.time()
        response = client.get('/healthz')
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 1.0
    
    def test_healthz_check_env_file_exists(self, client, temp_project_dir, monkeypatch):
        """Тест проверки существования .env файла"""
        monkeypatch.chdir(temp_project_dir)
        
        response = client.get('/healthz')
        data = response.get_json()
        
        assert data['checks']['env_file'] is True
    
    def test_healthz_check_local_config_exists(self, client, temp_project_dir, monkeypatch):
        """Тест проверки существования global.conf файла"""
        monkeypatch.chdir(temp_project_dir)
        
        response = client.get('/healthz')
        data = response.get_json()
        
        assert data['checks']['local_config'] is True


class TestHealthzWithMocks:
    """Тесты healthz с моками"""
    
    def test_healthz_when_global_config_unavailable(self, client, mocker):
        """Тест когда глобальный сервис конфигураций недоступен"""
        mocker.patch('k8s.healthz.check_global_config_available', return_value=False)
        
        response = client.get('/healthz')
        
        # Должен вернуть 503, так как критический компонент недоступен
        assert response.status_code == 503
        
        data = response.get_json()
        assert data['status'] is False
        assert 'issues' in data
    
    def test_healthz_when_env_file_missing(self, client, mocker):
        """Тест когда .env файл отсутствует"""
        mocker.patch('k8s.healthz.check_env_file_exists', return_value=False)
        mocker.patch('k8s.healthz.check_local_config_exists', return_value=True)
        mocker.patch('k8s.healthz.check_global_config_available', return_value=True)
        
        response = client.get('/healthz')
        
        assert response.status_code == 503
        data = response.get_json()
        assert data['status'] is False
    
    def test_healthz_when_local_config_missing(self, client, mocker):
        """Тест когда global.conf файл отсутствует"""
        mocker.patch('k8s.healthz.check_env_file_exists', return_value=True)
        mocker.patch('k8s.healthz.check_local_config_exists', return_value=False)
        mocker.patch('k8s.healthz.check_global_config_available', return_value=True)
        
        response = client.get('/healthz')
        
        assert response.status_code == 503
        data = response.get_json()
        assert data['status'] is False
# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import pytest
import time


pytestmark = pytest.mark.api


class TestHealthAPI:
    """Тесты для health API"""
    
    def test_healthz_endpoint(self, client):
        """Тест healthz эндпоинта"""
        response = client.get('/healthz')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['status'] is True
        assert 'Service is alive' in data['message']
    
    def test_readyz_endpoint(self, client):
        """Тест readyz эндпоинта"""
        response = client.get('/readyz')
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['status'] is True
        assert data['message'] == 'Service is ready to accept traffic'
    
    def test_healthz_response_time(self, client):
        """Тест времени ответа healthz"""
        start = time.time()
        response = client.get('/healthz')
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 1.0
    
    def test_readyz_response_time(self, client):
        """Тест времени ответа readyz"""
        start = time.time()
        response = client.get('/readyz')
        elapsed = time.time() - start
        
        assert response.status_code == 200
        assert elapsed < 1.0
    
    def test_healthz_returns_json(self, client):
        """Тест что healthz возвращает JSON"""
        response = client.get('/healthz')
        assert response.content_type == 'application/json'
    
    def test_readyz_returns_json(self, client):
        """Тест что readyz возвращает JSON"""
        response = client.get('/readyz')
        assert response.content_type == 'application/json'
    
    def test_healthz_only_get_allowed(self, client):
        """Тест что healthz принимает только GET"""
        methods = ['post', 'put', 'delete', 'patch', 'head']
        
        for method in methods:
            response = getattr(client, method)('/healthz')
            assert response.status_code == 403, f"Method {method} should be blocked"
    
    def test_readyz_only_get_allowed(self, client):
        """Тест что readyz принимает только GET"""
        methods = ['post', 'put', 'delete', 'patch', 'head']
        
        for method in methods:
            response = getattr(client, method)('/readyz')
            assert response.status_code == 403, f"Method {method} should be blocked"
    
    def test_healthz_response_contains_checks(self, client):
        """Тест что healthz содержит все проверки"""
        response = client.get('/healthz')
        data = response.get_json()
        
        checks = data['checks']
        assert 'env_file' in checks
        assert 'local_config' in checks
        assert 'global_config' in checks
    
    def test_readyz_response_contains_checks(self, client):
        """Тест что readyz содержит все проверки"""
        response = client.get('/readyz')
        data = response.get_json()
        
        checks = data['checks']
        assert 'env_file' in checks
        assert 'local_config' in checks
        assert 'global_config' in checks
        assert 'database_enabled' in checks
        assert 'database_initialized' in checks
        assert 'database_healthy' in checks
    
    def test_healthz_concurrent_requests(self, client):
        """Тест конкурентных запросов к healthz"""
        import concurrent.futures
        
        def make_request():
            return client.get('/healthz')
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(20)]
            results = [f.result() for f in futures]
        
        for response in results:
            assert response.status_code == 200
    
    def test_readyz_concurrent_requests(self, client):
        """Тест конкурентных запросов к readyz"""
        import concurrent.futures
        
        def make_request():
            return client.get('/readyz')
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(20)]
            results = [f.result() for f in futures]
        
        for response in results:
            assert response.status_code == 200
# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import pytest
import uuid
import concurrent.futures


pytestmark = pytest.mark.api


class TestIntegrationAPI:
    """Интеграционные тесты API"""
    
    def test_complete_request_flow(self, client, generate_rqid):
        """Тест полного потока запроса"""
        # 1. Проверка health
        health_response = client.get('/healthz')
        assert health_response.status_code == 200
        
        # 2. Проверка ready
        ready_response = client.get('/readyz')
        assert ready_response.status_code == 200
        
        # 3. Выполнение авторизованного запроса
        login_response = client.post('/v1/auth/login',
                                    json={
                                        'login': 'testuser@example.com',
                                        'password': 'securepassword123',
                                        'type': 'internal'
                                    },
                                    headers={
                                        'MODULE-ID': 'TEST-CONF',
                                        'Rqid': generate_rqid
                                    })
        
        assert login_response.status_code != 403
    
    def test_sequence_of_requests_same_rqid(self, client, generate_rqid):
        """Тест последовательности запросов с одинаковым Rqid"""
        headers = {
            'MODULE-ID': 'TEST-CONF',
            'Rqid': generate_rqid
        }
        
        for i in range(5):
            response = client.post('/v1/auth/login',
                                  json={
                                      'login': f'user{i}@example.com',
                                      'password': 'securepassword123',
                                      'type': 'internal'
                                  },
                                  headers=headers)
            
            assert response.status_code != 403
    
    def test_sequence_of_requests_different_rqid(self, client):
        """Тест последовательности запросов с разными Rqid"""
        for i in range(5):
            rqid = str(uuid.uuid4())
            response = client.post('/v1/auth/login',
                                  json={
                                      'login': f'user{i}@example.com',
                                      'password': 'securepassword123',
                                      'type': 'internal'
                                  },
                                  headers={
                                      'MODULE-ID': 'TEST-CONF',
                                      'Rqid': rqid
                                  })
            
            assert response.status_code != 403
    
    def test_concurrent_requests_to_login(self, client):
        """Тест конкурентных запросов к login эндпоинту"""
        def make_request(i):
            rqid = str(uuid.uuid4())
            return client.post('/v1/auth/login',
                              json={
                                  'login': f'user{i}@example.com',
                                  'password': 'securepassword123',
                                  'type': 'internal'
                              },
                              headers={
                                  'MODULE-ID': 'TEST-CONF',
                                  'Rqid': rqid
                              })
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, i) for i in range(20)]
            results = [f.result() for f in futures]
        
        for response in results:
            assert response.status_code != 403
    
    def test_concurrent_requests_to_secure_endpoint(self, client):
        """Тест конкурентных запросов к secure эндпоинту"""
        def make_request(i):
            rqid = str(uuid.uuid4())
            return client.post('/test/secure',
                              json={
                                  'username': f'user{i}',
                                  'password': 'password123'
                              },
                              headers={
                                  'MODULE-ID': 'TEST-MODULE',
                                  'Rqid': rqid
                              })
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, i) for i in range(20)]
            results = [f.result() for f in futures]
        
        for response in results:
            assert response.status_code != 403
    
    def test_mixed_endpoints_sequence(self, client, generate_rqid):
        """Тест последовательности запросов к разным эндпоинтам"""
        # GET запрос к healthz
        assert client.get('/healthz').status_code == 200
        
        # GET запрос к readyz
        assert client.get('/readyz').status_code == 200
        
        # GET запрос к test/ok
        assert client.get('/test/ok').status_code != 403
        
        # POST запрос к secure
        secure_response = client.post('/test/secure',
                                     json={'username': 'testuser', 'password': 'password123'},
                                     headers={
                                         'MODULE-ID': 'TEST-MODULE',
                                         'Rqid': generate_rqid
                                     })
        assert secure_response.status_code != 403
        
        # POST запрос к login
        login_response = client.post('/v1/auth/login',
                                    json={
                                        'login': 'testuser@example.com',
                                        'password': 'securepassword123',
                                        'type': 'internal'
                                    },
                                    headers={
                                        'MODULE-ID': 'TEST-CONF',
                                        'Rqid': generate_rqid
                                    })
        assert login_response.status_code != 403
    
    def test_error_recovery(self, client):
        """Тест восстановления после ошибочных запросов"""
        # Ошибочный запрос (неправильный метод)
        bad_response = client.post('/test/ok')
        assert bad_response.status_code == 403
        
        # Следующий корректный запрос должен работать
        good_response = client.get('/test/ok')
        assert good_response.status_code != 403
    
    def test_healthz_before_readyz(self, client):
        """Тест что healthz работает даже если readyz еще не прошел"""
        # healthz всегда должен работать
        health_response = client.get('/healthz')
        assert health_response.status_code == 200
        
        # readyz должен работать после инициализации
        ready_response = client.get('/readyz')
        assert ready_response.status_code == 200
    
    def test_long_running_sequence(self, client):
        """Тест длинной последовательности запросов"""
        for i in range(20):
            rqid = str(uuid.uuid4())
            
            # Разные типы запросов
            if i % 3 == 0:
                response = client.get('/healthz')
            elif i % 3 == 1:
                response = client.get('/readyz')
            else:
                response = client.get('/test/ok')
            
            assert response.status_code in [200, 403], f"Request {i} failed"
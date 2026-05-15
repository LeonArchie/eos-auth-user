# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

import pytest


pytestmark = pytest.mark.api


class TestValidationAPI:
    """Тесты для API валидации"""
    
    def test_secure_endpoint_valid(self, client, generate_rqid):
        """Тест secure эндпоинта с валидными данными"""
        response = client.post('/test/secure',
                              json={
                                  'username': 'testuser',
                                  'password': 'password123'
                              },
                              headers={
                                  'MODULE-ID': 'TEST-MODULE',
                                  'Rqid': generate_rqid
                              })
        
        assert response.status_code != 403
    
    def test_secure_endpoint_short_username(self, client, generate_rqid):
        """Тест secure эндпоинта с слишком коротким username (<3 символов)"""
        response = client.post('/test/secure',
                              json={
                                  'username': 'ab',
                                  'password': 'password123'
                              },
                              headers={
                                  'MODULE-ID': 'TEST-MODULE',
                                  'Rqid': generate_rqid
                              })
        
        assert response.status_code == 403
    
    def test_secure_endpoint_long_username(self, client, generate_rqid):
        """Тест secure эндпоинта с длинным username (20+ символов)"""
        response = client.post('/test/secure',
                              json={
                                  'username': 'a' * 21,
                                  'password': 'password123'
                              },
                              headers={
                                  'MODULE-ID': 'TEST-MODULE',
                                  'Rqid': generate_rqid
                              })
        
        assert response.status_code == 403
    
    def test_secure_endpoint_invalid_username_chars(self, client, generate_rqid):
        """Тест secure эндпоинта с недопустимыми символами в username"""
        response = client.post('/test/secure',
                              json={
                                  'username': 'user@name!',
                                  'password': 'password123'
                              },
                              headers={
                                  'MODULE-ID': 'TEST-MODULE',
                                  'Rqid': generate_rqid
                              })
        
        assert response.status_code == 403
    
    def test_secure_endpoint_missing_username(self, client, generate_rqid):
        """Тест secure эндпоинта с отсутствующим username"""
        response = client.post('/test/secure',
                              json={'password': 'password123'},
                              headers={
                                  'MODULE-ID': 'TEST-MODULE',
                                  'Rqid': generate_rqid
                              })
        
        assert response.status_code == 403
    
    def test_secure_endpoint_missing_password(self, client, generate_rqid):
        """Тест secure эндпоинта с отсутствующим password"""
        response = client.post('/test/secure',
                              json={'username': 'testuser'},
                              headers={
                                  'MODULE-ID': 'TEST-MODULE',
                                  'Rqid': generate_rqid
                              })
        
        assert response.status_code == 403
    
    def test_secure_endpoint_extra_field(self, client, generate_rqid):
        """Тест secure эндпоинта с лишним полем"""
        response = client.post('/test/secure',
                              json={
                                  'username': 'testuser',
                                  'password': 'password123',
                                  'extra': 'forbidden'
                              },
                              headers={
                                  'MODULE-ID': 'TEST-MODULE',
                                  'Rqid': generate_rqid
                              })
        
        assert response.status_code == 403
    
    def test_get_ok_endpoint(self, client):
        """Тест GET эндпоинта /test/ok"""
        response = client.get('/test/ok')
        assert response.status_code != 403
    
    def test_get_ok_endpoint_post_blocked(self, client):
        """Тест POST запроса к /test/ok (должен быть заблокирован)"""
        response = client.post('/test/ok')
        assert response.status_code == 403


class TestValidationAPIParameterized:
    """Параметризованные тесты для API валидации"""
    
    @pytest.mark.parametrize("username,should_pass", [
        ("user", True),
        ("username123", True),
        ("user_name", True),
        ("user123", True),
        ("a" * 20, True),  # Максимальная длина
        ("ab", False),     # Меньше 3 символов
        ("a" * 21, False), # Больше 20 символов
        ("user!", False),  # Недопустимый символ
        ("user@", False),  # Недопустимый символ
        ("", False),       # Пусто
    ])
    def test_secure_endpoint_various_usernames(self, client, generate_rqid, 
                                                username, should_pass):
        """Тест различных username"""
        response = client.post('/test/secure',
                              json={
                                  'username': username,
                                  'password': 'password123'
                              },
                              headers={
                                  'MODULE-ID': 'TEST-MODULE',
                                  'Rqid': generate_rqid
                              })
        
        if should_pass:
            assert response.status_code != 403
        else:
            assert response.status_code == 403
    
    @pytest.mark.parametrize("password,should_pass", [
        ("123456", True),
        ("a" * 6, True),
        ("a" * 100, True),
        ("short", False),   # Меньше 6 символов
        ("", False),        # Пусто
        ("a" * 5, False),   # 5 символов
    ])
    def test_secure_endpoint_various_passwords(self, client, generate_rqid,
                                                password, should_pass):
        """Тест различных password"""
        response = client.post('/test/secure',
                              json={
                                  'username': 'testuser',
                                  'password': password
                              },
                              headers={
                                  'MODULE-ID': 'TEST-MODULE',
                                  'Rqid': generate_rqid
                              })
        
        if should_pass:
            assert response.status_code != 403
        else:
            assert response.status_code == 403
#!/bin/bash

# SPDX-License-Identifier: AGPL-3.0-only WITH LICENSE-ADDITIONAL
# Copyright (C) 2025 Петунин Лев Михайлович

# Цветной вывод
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}    Запуск тестового пакета${NC}"
echo -e "${BLUE}========================================${NC}"

# Проверка виртуального окружения
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}Предупреждение: Виртуальное окружение не активировано${NC}"
fi

# Установка тестовых зависимостей
echo -e "${YELLOW}Установка тестовых зависимостей...${NC}"
pip install -q -r test/requirements-test.txt

if [ $? -ne 0 ]; then
    echo -e "${RED}Ошибка установки зависимостей${NC}"
    exit 1
fi

echo -e "${GREEN}Зависимости установлены${NC}"

# Запуск всех тестов
echo -e "\n${BLUE}1. Запуск всех тестов...${NC}"
pytest test/ -v

# Запуск только unit тестов
echo -e "\n${BLUE}2. Запуск unit тестов...${NC}"
pytest test/app/ -v -m "unit"

# Запуск только API тестов
echo -e "\n${BLUE}3. Запуск API тестов...${NC}"
pytest test/api/ -v -m "api"

# Запуск с отчетом о покрытии
echo -e "\n${BLUE}4. Запуск с отчетом о покрытии...${NC}"
pytest test/ -v --cov=. --cov-report=term --cov-report=html

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}    Все тесты завершены${NC}"
echo -e "${GREEN}    Отчет о покрытии: htmlcov/index.html${NC}"
echo -e "${GREEN}========================================${NC}"
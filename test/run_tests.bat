@echo off
chcp 65001 > nul
cd /d %~dp0

echo ========================================
echo     Запуск тестов
echo ========================================

echo.
echo Текущая директория: %CD%

echo.
echo Установка зависимостей...
pip install -q -r requirements-test.txt

echo.
echo Очистка кэша Python...
cd ..
for /d %%d in ("app\__pycache__" "test\__pycache__" "app\maintenance\__pycache__" "app\handlers\__pycache__" "app\k8s\__pycache__") do (
    if exist "%%d" rmdir /s /q "%%d" 2>nul
)
cd test

echo.
echo Запуск тестов...
python -m pytest -v --tb=short

echo.
echo Готово!
pause
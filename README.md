# University System Project

Небольшое Flask-приложение. Инструкция для запуска на локальной машине.

## Требования
- Python 3.10+ (желательно)
- pip

## Установка
```bash
# 1) Клонируй проект / распакуй папку
cd university_system_project

# 2) Создай и активируй виртуальное окружение
python -m venv venv
source venv/bin/activate  # macOS/Linux
# или для Windows:
# venv\Scripts\activate

# 3) Установи зависимости
pip install -r requirements.txt
```

## Запуск
```bash
python app.py
```
По умолчанию приложение стартует на `http://127.0.0.1:5000`.

## База данных
По умолчанию используется локальный SQLite-файл `database.db` в корне проекта.
Если нужен сброс базы — удали `database.db` и запусти приложение заново.

## Переменные окружения (необязательно)
Можно задать секретный ключ:
```bash
export SECRET_KEY="любая_строка"
```

## Примечания
- Если порт 5000 занят, можно изменить его в `app.py` в блоке `app.run(...)`.

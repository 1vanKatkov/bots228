#!/usr/bin/env python3
import sys
import os

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(__file__))

# Импортируем и запускаем основную функцию
from bot_number import main

if __name__ == "__main__":
    main()
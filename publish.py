#!/usr/bin/env python3
"""Обёртка для обратной совместимости. Используй: python manage.py publish"""
from manage import cmd_publish

if __name__ == "__main__":
    cmd_publish()

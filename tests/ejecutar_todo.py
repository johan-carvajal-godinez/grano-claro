# -*- coding: utf-8 -*-
"""Ejecuta toda la verificación del repositorio.

1. Auditoría estática de la versión actual y de la 1.0 (auditar_agentes.py).
2. Pruebas de extremo a extremo de los requisitos R1–R9 en la versión actual (probar_pagina.py).
3. Las mismas pruebas en la versión 1.0, que se conserva tal como se publicó.
4. Pruebas propias de la versión 1.1: vistas, cafés de Costa Rica y consola (probar_v1_1.py).

Uso: python3 tests/ejecutar_todo.py   (o: npm test)
Sale con código 1 si algo falla. Los fallos conocidos de la 1.0 se informan, pero no cuentan como fallo.
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASOS = [
    ('Auditoría estática (versión actual y 1.0)', ['tests/auditar_agentes.py']),
    ('Pruebas de extremo a extremo, versión actual', ['tests/probar_pagina.py', 'index.html']),
    ('Pruebas de extremo a extremo, versión 1.0', ['tests/probar_pagina.py', 'versions/v1.0/index.html']),
    ('Pruebas propias de la versión 1.1', ['tests/probar_v1_1.py']),
]


def main():
    resultados = []
    for titulo, args in PASOS:
        print(f'\n=== {titulo} ===', flush=True)
        inicio = time.time()
        codigo = subprocess.run([sys.executable, *args], cwd=ROOT).returncode
        resultados.append((titulo, codigo, time.time() - inicio))
    print('\n=== Resumen ===')
    for titulo, codigo, segundos in resultados:
        print(f'{"OK   " if codigo == 0 else "FALLA"}  {titulo} ({segundos:.0f} s)')
    return 0 if all(codigo == 0 for _, codigo, _ in resultados) else 1


if __name__ == '__main__':
    sys.exit(main())

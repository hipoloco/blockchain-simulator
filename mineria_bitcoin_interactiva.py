
#!/usr/bin/env python3
"""
Simulador interactivo de minería Bitcoin (CLI)
----------------------------------------------------------------------------

Características:
- PoW real: **SHA-256 doble** del header de 80 bytes.
- Aviso si repites un nonce que **ya produjo** un hash válido con la cantidad de ceros indicada.
- Corte automático por tiempo (no depende de que presiones ENTER).
- **Prompt estático** mientras corre el contador.
- Muestra solo el nombre de `blocks.json` si está en el mismo directorio que el script.
- Limpia la pantalla al comenzar a ingresar nonces y al finalizar el tiempo, **manteniendo la cabecera**.
- **Beep** al encontrar un hash válido (transversal: Windows / Unix).

Uso:
  python mineria_bitcoin_interactiva.py --blocks blocks.json --segundos 60 --dificultad 1 --verbose
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import struct
import sys
import time
import getpass
from dataclasses import dataclass
from typing import List, Dict, Any

from threading import Thread, Event
from queue import Queue, Empty
from pathlib import Path


# --------------------------------------------------------------------------------------
# Utilidades de consola
# --------------------------------------------------------------------------------------

def clear_screen() -> None:
    """Limpia la consola en Windows (cls) o Unix-like (clear)."""
    os.system('cls' if os.name == 'nt' else 'clear')


def beep(freq: int = 2200, dur_ms: int = 120) -> None:
    """Beep agudo (mejor esfuerzo, multiplataforma).
    - Windows: winsound.Beep(frecuencia, duración_ms).
    - Unix/macOS: intenta SoX ('play -n synth'), si no, usa BEL ('\a').
      Nota: la campana puede estar silenciada en la terminal.
    """
    try:
        if os.name == 'nt':
            try:
                import winsound
                winsound.Beep(int(freq), int(dur_ms))
            except Exception:
                print('\a', end='', flush=True)
        else:
            import shutil, subprocess
            play = shutil.which('play')
            if play:
                dur = max(0.02, min(1.0, dur_ms/1000.0))
                subprocess.Popen([play, '-q', '-n', 'synth', str(dur), 'sine', str(int(freq))])
            else:
                print('\a', end='', flush=True)
    except Exception:
        # Último recurso
        try:
            print('\a', end='', flush=True)
        except Exception:
            pass


# --------------------------------------------------------------------------------------
# Entrada no bloqueante (hilo lector)
# --------------------------------------------------------------------------------------

class _InputThread(Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.q = Queue()
        self.stop_event = Event()

    def run(self):
        while not self.stop_event.is_set():
            try:
                s = input()
            except (EOFError, KeyboardInterrupt):
                break
            self.q.put(s)

    def get_line(self, timeout: float | None):
        try:
            return self.q.get(timeout=timeout)
        except Empty:
            return None


# --------------------------------------------------------------------------------------
# Datos y utilidades
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class BlockHeader:
    name: str
    height: int
    version: int
    prev_block: str
    merkle_root: str
    timestamp: int
    bits: int  # compact target (uint32)


def _little_endian_hex_to_bytes(hex_str: str) -> bytes:
    b = bytes.fromhex(hex_str)
    return b[::-1]


def serialize_header(header: BlockHeader, nonce: int) -> bytes:
    """Serializa el header (80 bytes) en little-endian, como en Bitcoin."""
    assert 0 <= header.version <= 0xFFFFFFFF
    assert 0 <= header.timestamp <= 0xFFFFFFFF
    assert 0 <= header.bits <= 0xFFFFFFFF
    assert 0 <= nonce <= 0xFFFFFFFF
    raw = struct.pack("<L", header.version)
    raw += _little_endian_hex_to_bytes(header.prev_block)
    raw += _little_endian_hex_to_bytes(header.merkle_root)
    raw += struct.pack("<L", header.timestamp)
    raw += struct.pack("<L", header.bits)
    raw += struct.pack("<L", nonce)
    if len(raw) != 80:
        raise ValueError("Header mal serializado (no mide 80 bytes)")
    return raw


def sha256d(data: bytes) -> bytes:
    """SHA256(SHA256(data)) — hashing real de PoW sobre el header en Bitcoin (big-endian)."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def display_hash(hex_bytes: bytes) -> str:
    """Muestra el hash al estilo explorador (bytes invertidos a hex)."""
    return hex_bytes[::-1].hex()


def _is_hex_64(s: str) -> bool:
    if not isinstance(s, str) or len(s) != 64:
        return False
    try:
        int(s, 16)
        return True
    except Exception:
        return False


def load_blocks_from_json(path: str) -> List[BlockHeader]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"No se encontró el archivo {path}. Proporcione --blocks con la ruta correcta.")
    with open(path, "r", encoding="utf-8") as f:
        parsed = json.load(f)
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("blocks.json debe ser una lista no vacía de objetos de bloque.")
    blocks: List[BlockHeader] = []
    for i, obj in enumerate(parsed):
        name = str(obj.get("name") or obj.get("label") or f"Block #{obj.get('height', '?')}")
        height = int(obj.get("height", -1))
        version = int(obj["version"])
        prev_block = str(obj["prev_block"]).lower()
        merkle_root = str(obj["merkle_root"]).lower()

        bits_val = obj.get("bits")
        if bits_val is None and obj.get("bits_hex"):
            bits_val = int(str(obj["bits_hex"]), 16)
        bits = int(bits_val)

        timestamp = int(obj["timestamp"])

        if not _is_hex_64(prev_block):
            raise ValueError(f"[blocks.json item {i}] prev_block inválido (debe ser hex de 64 chars).")
        if not _is_hex_64(merkle_root):
            raise ValueError(f"[blocks.json item {i}] merkle_root inválido (debe ser hex de 64 chars).")
        if not (0 <= bits <= 0xFFFFFFFF):
            raise ValueError(f"[blocks.json item {i}] bits fuera de rango uint32.")
        if not (0 <= version <= 0xFFFFFFFF):
            raise ValueError(f"[blocks.json item {i}] version fuera de rango uint32.")
        if not (0 <= timestamp <= 0xFFFFFFFF):
            raise ValueError(f"[blocks.json item {i}] timestamp fuera de rango uint32.")

        blocks.append(BlockHeader(
            name=name,
            height=height,
            version=version,
            prev_block=prev_block,
            merkle_root=merkle_root,
            timestamp=timestamp,
            bits=bits,
        ))
    return blocks


def choose_block_from_file(path: str) -> BlockHeader:
    pool = load_blocks_from_json(path)
    return random.choice(pool)


def header_text(block: BlockHeader, segundos: int, dificultad: int, blocks_path: str) -> str:
    # Mostrar solo el nombre si blocks.json está en el mismo directorio que este script
    script_dir = Path(__file__).resolve().parent
    blocks_res = Path(blocks_path).resolve()
    if blocks_res.parent == script_dir:
        fuente = blocks_res.name
    else:
        fuente = str(blocks_res)

    lines = []
    lines.append("="*72)
    lines.append("🧱  Simulador de Minería Bitcoin (demo didáctica)")
    lines.append("="*72)
    lines.append(f"Fuente de bloques: {fuente}")
    lines.append("Bloque asignado:")
    lines.append(f"  • Nombre:    {block.name}")
    if block.height >= 0:
        lines.append(f"  • Altura:    {block.height}")
    lines.append(f"  • Versión:   {block.version}")
    lines.append(f"  • PrevHash:  {block.prev_block}")
    lines.append(f"  • Merkle:    {block.merkle_root}")
    lines.append(f"  • Timestamp: {block.timestamp} (epoch)")
    lines.append(f"  • Bits:      0x{block.bits:08x} ({block.bits})")
    lines.append("")
    lines.append(f"Tiempo total: {segundos}s | Dificultad: {'0'*dificultad}")
    return "\n".join(lines)


def print_intro(block: BlockHeader, segundos: int, dificultad: int, blocks_path: str):
    print(header_text(block, segundos, dificultad, blocks_path))
    print()
    print("Reglas del juego:")
    print(f"  1) Tienes {segundos} segundos para ingresar nonces (0 a 4.294.967.295).")
    print(f"  2) Cada intento calcula SHA256d(header) con tu nonce.")
    print(f"  3) Se registran los hashes que comienzan con {'0'*dificultad}.")
    print("\nPulsa ENTER para comenzar el cronómetro…", end="")
    getpass.getpass("")  # input oculto para no mostrar el ENTER

def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulador interactivo de minería Bitcoin (usa blocks.json real)")
    parser.add_argument("--blocks", type=str, default="blocks.json", help="Ruta al archivo blocks.json (requerido)")
    parser.add_argument("--segundos", type=int, default=60, help="Duración del juego (por defecto 60)")
    parser.add_argument("--dificultad", type=int, default=1, help="Cantidad de ceros iniciales requeridos (por defecto 1)")
    parser.add_argument("--verbose", action="store_true", help="Muestra el hash de cada intento")
    args = parser.parse_args(argv)

    if args.dificultad < 1:
        print("La dificultad debe ser >= 1")
        return 2

    try:
        block = choose_block_from_file(args.blocks)
    except Exception as e:
        print(f"Error al cargar '{args.blocks}': {e}")
        return 2

    # Intro y espera de ENTER
    print_intro(block, args.segundos, args.dificultad, args.blocks)

    # Limpiar pantalla y reimprimir cabecera para comenzar
    clear_screen()
    print(header_text(block, args.segundos, args.dificultad, args.blocks))
    print()
    print("Ingresa nonces y presiona ENTER (escribe 'salir' para terminar).")
    print("> ", end="", flush=True)

    aciertos: List[Dict[str, Any]] = []
    inicio = time.monotonic()
    intentos = 0

    # Beeps de cuenta regresiva (últimos 5s)
    next_beep_at = min(5, max(1, int(args.segundos)))

    # Track nonces que ya dieron acierto
    nonces_validos = set()

    # Lector no bloqueante
    inp = _InputThread()
    inp.start()

    # Bucle con timeout duro
    while True:
        restante = args.segundos - (time.monotonic() - inicio)
        if restante <= 0:
            break

        # Beep agudo por segundo en los últimos 5 segundos
        if next_beep_at >= 1 and restante <= next_beep_at and restante > 0:
            beep(2200, 120)
            next_beep_at -= 1

        # Espera input sin imprimir prompts repetidos
        timeout = max(0.05, min(0.5, restante))
        s = inp.get_line(timeout=timeout)
        if s is None:
            continue

        # Procesar entrada
        s = s.strip()
        if s == "":
            print("> ", end="", flush=True)
            continue
        if s.lower() in ("salir", "exit", "quit"):
            break

        # Rechequear tiempo: si ya terminó, cortamos sin procesar la línea
        if (time.monotonic() - inicio) >= args.segundos:
            break

        if not (s.isdigit() and 0 <= int(s) <= 0xFFFFFFFF):
            print("  ⚠️  Debe ser un entero decimal entre 0 y 4294967295 (2^32-1).")
            print("> ", end="", flush=True)
            continue

        nonce = int(s)

        if nonce in nonces_validos:
            print("  ⚠️  Ya habías encontrado un hash válido con este nonce. Prueba otro distinto.")
            print("> ", end="", flush=True)
            continue

        header_bytes = serialize_header(block, nonce)
        h = sha256d(header_bytes)  # SHA-256d (doble SHA-256)
        h_hex = display_hash(h)
        intentos += 1

        if args.verbose:
            print(f"\n  Hash: {h_hex}")

        if h_hex.startswith("0" * args.dificultad):
            aciertos.append({"nonce": nonce, "hash": h_hex})
            nonces_validos.add(nonce)
            beep()
            print(f"  ✅ ¡Cumple! ({'0'*args.dificultad}…): nonce={nonce}")

        # Reponer prompt estático SIEMPRE (también cuando no hay acierto y no hay verbose)
        print("> ", end="", flush=True)

    # Parar lector (best-effort)
    try:
        inp.stop_event.set()
    except Exception:
        pass

    # Limpiar pantalla y reimprimir cabecera para mostrar resultados
    clear_screen()
    print(header_text(block, args.segundos, args.dificultad, args.blocks))

    print("\n" + "="*72)
    print(f"Tiempo agotado. Intentos totales: {intentos}")
    print(f"Aciertos (hashes que comienzan con {'0'*args.dificultad}): {len(aciertos)}")
    if aciertos:
        print("-"*72)
        print("Nonce".ljust(14), "Hash")
        print("-"*72)
        for item in aciertos:
            print(str(item['nonce']).ljust(14), item['hash'])
    else:
        print("No se encontraron hashes que cumplan la condición.")
    print("-"*72)
    print("Tip didáctico: en Bitcoin real no se cuenta el número de ceros,")
    print("se exige que el hash sea menor que un *target* (campo `bits`).")
    print("\nGracias por minar ✨")
    return 0


if __name__ == "__main__":
    sys.exit(main())

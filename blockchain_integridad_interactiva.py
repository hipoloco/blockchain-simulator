#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
blockchain_integridad_interactiva.py
------------------------------------
Demostración interactiva de *integridad en cadena* con bloques encadenados por hash.

Objetivo didáctico:
- Mostrar cómo un cambio en los datos de un bloque altera su hash y rompe la cadena
  (el *prev_hash* del siguiente bloque ya no coincide).
- Tras alterar un bloque, tenés una ventana cronometrada para ajustar el nonce y
  recuperar un hash que cumpla la dificultad; si lo lográs, la corrección se
  propaga hacia adelante bloque por bloque (cada uno con su ventana).
- El **último bloque NO se puede alterar**.
- Visual y rápido: caja por bloque, colores, y estado OK/ROTO.

Notas:
- Hash de bloque calculado con **SHA-256 doble** (SHA256d) sobre los campos:
  index | prev_hash | timestamp | data | nonce.
- Dificultad = cantidad de ceros al inicio del hash (valor bajo para demo).

Uso:
  python3 blockchain_integridad_interactiva.py
  # argumentos (opcionales):
  python3 blockchain_integridad_interactiva.py --bloques 6 --dificultad 2 --tiempo-fix 30

Controles en ejecución:
  [V] Ver cadena     [A] Alterar bloque
  [R] Reiniciar      [Q] Salir
"""
from __future__ import annotations

import argparse
import getpass
import re
import hashlib
import os
import random
import sys
import time
from dataclasses import dataclass
from typing import List, Optional

# ---- Entrada no bloqueante (como en el minero) ----
# Config UI (se actualiza desde main con --tiempo-fix)
UI_TIMEBOX_SECONDS = 30

# ---------------------------------- Utilidades UI ----------------------------------
ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "cyan": "\033[36m",
    "dim": "\033[2m",
    "box": "\033[90m",
}

# Utilidades para medir y ajustar texto ignorando secuencias ANSI
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)

def visible_len(s: str) -> int:
    return len(strip_ansi(s))

def _wcwidth(ch: str) -> int:
    """Estimación de ancho de celda aproximada y práctica.
    - Controles y combinantes: 0
    - ZWJ (\u200d) y VS16 (\uFE0F): 0
    - EAW Wide/Fullwidth: 2
    - Símbolos gráficos (So) ambiguos y SMP (>= U+1F300): 2
    - Resto: 1
    """
    import unicodedata
    if not ch:
        return 0
    if unicodedata.combining(ch):
        return 0
    cat = unicodedata.category(ch)
    if cat.startswith('C'):
        return 0
    if ch in ('\u200d', '\uFE0F'):
        return 0
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ('W', 'F'):
        return 2
    if ord(ch) >= 0x1F300:
        return 2
    if cat == 'So' and eaw in ('W', 'F', 'A'):
        return 2
    return 1

def display_width(text: str) -> int:
    s = strip_ansi(text)
    w = 0
    for ch in s:
        w += _wcwidth(ch)
    return w

def fit_and_pad(content: str, width: int = 76) -> str:
    """Trunca y rellena a 'width' columnas (emoji/ANSI safe)."""
    out: list[str] = []
    i = 0
    cur = 0
    s = content
    while i < len(s):
        if s[i] == "\x1b":
            m = ANSI_RE.match(s, i)
            if m:
                out.append(m.group(0))
                i = m.end()
                continue
        ch = s[i]
        w = _wcwidth(ch)
        if cur + w > width:
            # agregar elipsis si cabe
            ell = "..."
            ell_w = display_width(ell)
            if width >= ell_w:
                # recortar out para dejar sitio alipsis
                temp = "".join(out)
                new_out: list[str] = []
                cur2 = 0
                j = 0
                while j < len(temp) and cur2 < (width - ell_w):
                    if temp[j] == "\x1b":
                        m2 = ANSI_RE.match(temp, j)
                        if m2:
                            new_out.append(m2.group(0))
                            j = m2.end()
                            continue
                    ch2 = temp[j]
                    w2 = _wcwidth(ch2)
                    if cur2 + w2 > (width - ell_w):
                        break
                    new_out.append(ch2)
                    cur2 += w2
                    j += 1
                new_out.append(ell)
                out = new_out
                cur = cur2 + ell_w
            break
        else:
            out.append(ch)
            cur += w
            i += 1
    # pad espacios
    pad = max(0, width - cur)
    if pad:
        out.append(" " * pad)
        cur += pad
    return "".join(out)

# ---------------------- Entrada no bloqueante por plataforma -----------------------
def _get_line_nb_posix(timeout: Optional[float]) -> Optional[str]:
    """Devuelve una línea si hay disponible en stdin dentro del timeout; si no, None.
    Usa select.select, por lo que requiere ENTER para completar la línea."""
    try:
        import select
        r, _, _ = select.select([sys.stdin], [], [], timeout)
        if r:
            s = sys.stdin.readline()
            return s.rstrip("\r\n")
        return None
    except Exception:
        return None

class _NBInputWin:
    """Acumulador de línea con polling mediante msvcrt en Windows.
    Echo manual, soporte básico de backspace y enter."""
    def __init__(self):
        import msvcrt  # type: ignore
        self.msvcrt = msvcrt
        self.buf: List[str] = []

    def get_line(self, timeout: float | None) -> Optional[str]:
        if timeout is None:
            timeout = 0.1
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            while self.msvcrt.kbhit():
                ch = self.msvcrt.getwch()
                if ch in ("\r", "\n"):
                    print()  # mover a nueva línea tras ENTER
                    s = "".join(self.buf)
                    self.buf.clear()
                    return s
                # Teclas especiales (flechas, etc.) vienen con prefijo \x00 o \xe0
                if ch in ("\x00", "\xe0"):
                    # Consumir el siguiente código y continuar
                    try:
                        _ = self.msvcrt.getwch()
                    except Exception:
                        pass
                    continue
                if ch == "\x08":  # backspace
                    if self.buf:
                        self.buf.pop()
                        # borrar visualmente: retroceso, espacio, retroceso
                        print("\b \b", end="", flush=True)
                    continue
                if ch == "\x03":  # Ctrl+C
                    raise KeyboardInterrupt
                # Agregar carácter normal
                self.buf.append(ch)
                print(ch, end="", flush=True)
            # dormir un poco para no monopolizar CPU
            time.sleep(0.01)
        return None

def supports_ansi() -> bool:
    if os.name == "nt":
        return True
    return sys.stdout.isatty()

def color(s: str, c: str) -> str:
    if supports_ansi() and c in ANSI:
        return ANSI[c] + s + ANSI["reset"]
    return s

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def beep(freq: int = 2200, dur_ms: int = 120):
    """Beep (Windows: winsound.Beep; otros: BEL '\\a')."""
    try:
        if os.name == "nt":
            import winsound
            winsound.Beep(int(freq), int(dur_ms))
        else:
            print("\a", end="", flush=True)
    except Exception:
        pass

# ------------------------------- Lógica de bloques ---------------------------------
@dataclass
class Block:
    index: int
    prev_hash: str
    timestamp: int
    data: str
    nonce: int = 0
    hash: str = ""

    def serialize(self) -> bytes:
        # Concatenación determinista (demo pedagógica)
        s = f"{self.index}|{self.prev_hash}|{self.timestamp}|{self.data}|{self.nonce}".encode("utf-8")
        return s

def sha256d(b: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()

def hex_hash(b: bytes) -> str:
    return b.hex()

def compute_hash(block: Block) -> str:
    return hex_hash(sha256d(block.serialize()))

def mine_block(block: Block, dificultad: int, max_tries: int = 10_000_000) -> Block:
    prefix = "0" * max(0, dificultad)
    tries = 0
    if block.hash and block.hash.startswith(prefix):
        return block
    while tries < max_tries:
        block.nonce = (block.nonce + 1) & 0xFFFFFFFF
        block.hash = compute_hash(block)
        if block.hash.startswith(prefix):
            return block
        tries += 1
    return block

def valid_link(prev: Block, curr: Block) -> bool:
    return curr.prev_hash == prev.hash

def meets_difficulty(b: Block, dificultad: int) -> bool:
    if dificultad <= 0:
        return True
    pref = "0" * dificultad
    return isinstance(b.hash, str) and b.hash.startswith(pref)

# ------------------------------ Cadena de demo -------------------------------------
DEMO_DATA = [
    "Transferencias salariales",
    "Pago proveedor A",
    "Devolución cliente",
    "Premio trimestral",
    "Ajuste contable",
    "Compra de insumos",
    "Factura #8421",
    "Reembolso viáticos",
]

class DemoChain:
    def __init__(self, n_blocks: int = 5, dificultad: int = 2, seed: int = 42):
        random.seed(seed)
        self.dificultad = dificultad
        self.blocks: List[Block] = []
        self._build(n_blocks)

    def _build(self, n: int):
        self.blocks = []
        prev_hash = "0"*64
        now = int(time.time())
        for i in range(n):
            data = DEMO_DATA[i % len(DEMO_DATA)]
            b = Block(index=i, prev_hash=prev_hash, timestamp=now + i*60, data=data, nonce=0)
            b = mine_block(b, self.dificultad)
            prev_hash = b.hash
            self.blocks.append(b)

    def reset(self, n_blocks: Optional[int] = None, dificultad: Optional[int] = None):
        if n_blocks is None:
            n_blocks = len(self.blocks)
        if dificultad is None:
            dificultad = self.dificultad
        self.dificultad = dificultad
        self._build(n_blocks)

    def tamper(self, idx: int, new_data: Optional[str] = None):
        b = self.blocks[idx]
        if new_data is None:
            new_data = b.data + " *alterado*"
        b.data = new_data
        # Recalcular hash del bloque ALTERADO (sin minado) para evidenciar la rotura
        b.hash = compute_hash(b)

    def propagate_after_fix(self, start_idx: int, timebox_seconds: int = 30) -> bool:
        """
        Desde start_idx+1 en adelante:
        - Actualiza prev_hash con el hash del bloque anterior (ya corregido).
        - Recalcula hash con el *mismo nonce actual*.
        - Si no cumple, ofrece 'timebox_seconds' para que la persona ingrese un nonce válido.
        - Si el tiempo se agota en algún paso, retorna False (se detiene la propagación).
        - Si llega al último bloque, retorna True.
        """
        prefix = "0" * max(0, self.dificultad)
        for j in range(start_idx + 1, len(self.blocks)):
            curr = self.blocks[j]
            prev = self.blocks[j-1]
            curr.prev_hash = prev.hash               # encadenar con el nuevo hash
            curr.hash = compute_hash(curr)           # recomputar con el mismo nonce

            # Refrescar visual después de enlazar y recomputar
            show_chain(self)

            if curr.hash.startswith(prefix):
                continue                             # ya cumple, avanzar

            ok = timebox_fix_block(curr, self.dificultad, timebox_seconds, prompt_label=f"Bloque {j}")
            # Refrescar visual tras intento (éxito o no)
            show_chain(self)
            if not ok:
                return False
        return True

# --------------------------------- Renderizado -------------------------------------
def box_block(b: Block, status_ok: bool, dificultad: int) -> str:
    status = color("✅ OK", "green") if status_ok else color("❌ ROTO", "red")
    lines = []
    top = "┌" + "─"*77 + "┐"
    bot = "└" + "─"*77 + "┘"
    lines.append(color(top, "box"))
    estado = f"idx: {b.index:<3}  ts: {b.timestamp:<10}  estado: {status}  dificultad: {color(str(dificultad),'cyan')}"
    lines.append("│ " + fit_and_pad(estado, 76) + "│")
    lines.append("│ " + fit_and_pad(f"prev_hash: {b.prev_hash}", 76) + "│")
    lines.append("│ " + fit_and_pad(f"data     : {b.data}", 76) + "│")
    lines.append("│ " + fit_and_pad(f"nonce    : {b.nonce}", 76) + "│")
    lines.append("│ " + fit_and_pad(f"hash     : {b.hash}", 76) + "│")
    lines.append(color(bot, "box"))
    return "\n".join(lines)

def show_chain(chain: DemoChain):
    clear()
    # Cabecera estilo minero + resumen
    print("="*72)
    print("🧱  Integridad de Cadena (demo didáctica)")
    print("="*72)
    zeros = "0"*chain.dificultad if chain.dificultad > 0 else "—"
    print(f"Bloques: {len(chain.blocks)} | Dificultad: {chain.dificultad} (prefijo {zeros}) | Tiempo fix: {UI_TIMEBOX_SECONDS}s")
    print()

    broken_cascade = False
    first_broken_idx = None

    for i, b in enumerate(chain.blocks):
        # 1) enlace válido con bloque anterior
        link_ok = True if i == 0 else valid_link(chain.blocks[i-1], b)
        # 2) dificultad válida en *este* bloque
        diff_ok = meets_difficulty(b, chain.dificultad)
        # 3) estado final con cascada
        status_ok = (not broken_cascade) and link_ok and diff_ok
        if not status_ok and not broken_cascade:
            broken_cascade = True
            first_broken_idx = i
        print(box_block(b, status_ok, chain.dificultad))

    print()
    if first_broken_idx is not None:
        print(color(f"⚠️  Cadena rota a partir del bloque {first_broken_idx}.", "red"))
    else:
        print(color("✅ Cadena íntegra.", "green"))
    print()

# -------------------------- Ventanas cronometradas (no bloqueante) -----------------
def timebox_fix_block(block: Block, dificultad: int, seconds: int = 30, prompt_label: str = "Bloque") -> bool:
    """
    Ventana de tiempo para que la persona ingrese un nonce que produzca un hash
    con 'dificultad' ceros al inicio. Entrada no bloqueante y prompt estático.
    Beeps en los últimos 5s.
    """
    prefix = "0" * max(0, dificultad)
    inicio = time.monotonic()
    next_beep_at = min(5, int(seconds))

    print(f"[{prompt_label}] Tenés {seconds}s para ingresar nonces. (ENTER para probar, 'salir' cancela)")
    print("> ", end="", flush=True)

    # Preparar lector no bloqueante específico por plataforma
    nb_win = None
    if os.name == "nt":
        try:
            nb_win = _NBInputWin()
        except Exception:
            nb_win = None

    while True:
        restante = seconds - (time.monotonic() - inicio)  # float
        if restante <= 0:
            print("\n⏱️  Tiempo agotado para", prompt_label)
            try: inp.stop_event.set()
            except Exception: pass
            return False

        # Beep agudo por segundo en los últimos 5s (independiente del prompt)
        if next_beep_at >= 1 and restante <= next_beep_at and restante > 0:
            beep(2200, 120)
            next_beep_at -= 1

        # Espera input sin bloquear el contador
        timeout = max(0.05, min(0.5, restante))
        if os.name == "nt" and nb_win is not None:
            s = nb_win.get_line(timeout)
        else:
            s = _get_line_nb_posix(timeout)
        if s is None:
            continue

        s = s.strip()
        if s.lower() in ("salir", "exit", "quit"):
            return False

        # Chequeo de expiración justo antes de procesar
        if (time.monotonic() - inicio) >= seconds:
            print("\n⏱️  Tiempo agotado para", prompt_label)
            try: inp.stop_event.set()
            except Exception: pass
            return False

        if not (s.isdigit() and 0 <= int(s) <= 0xFFFFFFFF):
            print("  ⚠️  Debe ser un entero decimal entre 0 y 4294967295 (2^32-1).")
            print("> ", end="", flush=True)
            continue

        nonce = int(s)
        block.nonce = nonce
        block.hash = compute_hash(block)

        if block.hash.startswith(prefix):
            print(f"  ✅ ¡Hash válido para {prompt_label}! ({'0'*dificultad}…)")
            beep(2200, 120)
            try:
                getpass.getpass("Nonce correcto. Presiona ENTER para continuar...")
            except Exception:
                input("Nonce correcto. ENTER para continuar...")
            return True
        else:
            print("  ❌ No cumple. Intenta otro nonce.")
            print("> ", end="", flush=True)

# ----------------------------------- Menú ------------------------------------------
def prompt_int(msg: str, lo: int, hi: int) -> int:
    while True:
        s = input(msg).strip()
        if not s.isdigit():
            print("  ⚠️  Ingrese un número válido.")
            continue
        v = int(s)
        if not (lo <= v <= hi):
            print(f"  ⚠️  Debe estar entre {lo} y {hi}.")
            continue
        return v

def main():
    global UI_TIMEBOX_SECONDS

    parser = argparse.ArgumentParser(description="Demo visual de integridad de cadena con hashes enlazados")
    parser.add_argument("--bloques", type=int, default=5, help="Cantidad de bloques iniciales (por defecto 5)")
    parser.add_argument("--dificultad", type=int, default=2, help="Ceros iniciales requeridos en el hash (por defecto 2)")
    parser.add_argument("--tiempo-fix", type=int, default=30, help="Segundos para corregir nonces tras alteración/propagación (por defecto 30)")
    args = parser.parse_args()

    if args.dificultad < 0:
        print("La dificultad debe ser >= 0")
        return 2

    UI_TIMEBOX_SECONDS = max(1, int(args.tiempo_fix))

    chain = DemoChain(n_blocks=args.bloques, dificultad=args.dificultad)

    while True:
        show_chain(chain)
        last_idx = len(chain.blocks) - 1
        print(f"Opciones:  [V] Ver  [A] Alterar  [R] Reiniciar  [Q] Salir")
        op = input("> ").strip().lower()

        if op in ("q", "quit", "salir"):
            break

        elif op in ("v", ""):
            continue  # ya se muestra en cada iteración

        elif op == "r":
            print("Reiniciando cadena...")
            time.sleep(0.4)
            chain.reset(n_blocks=args.bloques, dificultad=args.dificultad)

        elif op == "a":
            # No se puede alterar el último bloque
            if last_idx <= 0:
                print("  ⚠️  No hay suficientes bloques para alterar.")
                time.sleep(0.8)
                continue
            idx = prompt_int(f"Seleccione índice de bloque a ALTERAR (0..{last_idx-1}, el último NO se altera): ", 0, last_idx-1)
            original = chain.blocks[idx].data
            nuevo = input(f"Nuevo 'data' (ENTER para marcar como '*alterado*', actual: '{original}'): ").strip()
            chain.tamper(idx, new_data=(nuevo if nuevo else None))

            # Mostrar cadena rota y abrir ventana cronometrada para corregir nonce de ese bloque
            show_chain(chain)
            print(color(f"Has alterado el Bloque {idx}. Tenés {args.tiempo_fix}s para corregir su nonce.", "yellow"))
            ok = timebox_fix_block(chain.blocks[idx], chain.dificultad, args.tiempo_fix, prompt_label=f"Bloque {idx}")

            # Reimprimir tras la ventana (éxito o no)
            show_chain(chain)

            if not ok:
                input("ENTER para continuar…")
                continue  # se abandona la propagación

            # Propagación hacia adelante (cada paso refresca la vista)
            print(color("Propagando la corrección hacia los bloques siguientes…", "cyan"))
            ok2 = chain.propagate_after_fix(idx, timebox_seconds=args.tiempo_fix)
            show_chain(chain)
            if ok2:
                print(color("✅ Cadena reparada hasta el último bloque.", "green"))
            else:
                print(color("⏱️  Reparación interrumpida por tiempo agotado en algún bloque.", "yellow"))
            input("ENTER para continuar…")

        else:
            print("  ⚠️  Opción no reconocida.")
            time.sleep(0.6)

    print("¡Gracias!")
    return 0

if __name__ == "__main__":
    sys.exit(main())

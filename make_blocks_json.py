#!/usr/bin/env python3
"""
make_blocks_json.py
Desc: Fetch real Bitcoin block headers for a list of heights and save to blocks.json.
Requires: Python 3.8+, requests
Usage:
  python make_blocks_json.py                # picks N random heights from chain (default 20)
  python make_blocks_json.py 0 1 2 210000  # or pass your own heights
Data sources:
  - blockchain.info API 'block-height' + 'rawblock' endpoints.
"""
import sys, json, time
from typing import List, Dict
import random
import requests

BLOCK_HEIGHT_URL = "https://blockchain.info/block-height/{height}?format=json"
RAWBLOCK_URL = "https://blockchain.info/rawblock/{block_hash}"
HTTP_HEADERS = {"User-Agent": "blockchain-simulator/1.0 (+https://github.com/hipoloco/blockchain-simulator)"}
MAX_RETRIES = 5
BASE_DELAY = 0.5  # seconds
MAX_DELAY = 10.0

def _request_get(url: str, timeout: float = 20.0) -> requests.Response:
    """GET con reintentos exponenciales y jitter para 429/5xx/errores transitorios."""
    attempt = 0
    while True:
        try:
            resp = requests.get(url, timeout=timeout, headers=HTTP_HEADERS)
            # Reintentar en 429 o 5xx
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                if attempt >= MAX_RETRIES:
                    resp.raise_for_status()
                    return resp
                delay = min(MAX_DELAY, BASE_DELAY * (2 ** attempt)) + random.uniform(0, 0.25)
                print(f"[retry] {resp.status_code} GET {url} -> esperando {delay:.2f}s…")
                time.sleep(delay)
                attempt += 1
                continue
            resp.raise_for_status()
            return resp
        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt >= MAX_RETRIES:
                raise
            delay = min(MAX_DELAY, BASE_DELAY * (2 ** attempt)) + random.uniform(0, 0.25)
            print(f"[retry] {e.__class__.__name__} GET {url} -> esperando {delay:.2f}s…")
            time.sleep(delay)
            attempt += 1

RANDOM_COUNT_DEFAULT = 20

def get_block_hash_by_height(height: int) -> str:
    resp = _request_get(BLOCK_HEIGHT_URL.format(height=height), timeout=20)
    resp.raise_for_status()
    data = resp.json()
    blocks = data.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError(f"Respuesta sin 'blocks' para height={height}")
    # pick the block with matching height (main chain)
    for blk in blocks:
        if isinstance(blk, dict) and blk.get("height") == height and blk.get("hash"):
            return str(blk["hash"])
    # fallback: if none matches by height, prefer first with 'hash'
    for blk in blocks:
        if isinstance(blk, dict) and blk.get("hash"):
            return str(blk["hash"])
    raise ValueError(f"No se encontró 'hash' en blocks para height={height}")

def get_latest_height() -> int:
    """Obtiene la altura más reciente de la cadena (mainnet)."""
    url = "https://blockchain.info/q/getblockcount"
    resp = _request_get(url, timeout=20)
    resp.raise_for_status()
    text = resp.text.strip()
    try:
        h = int(text)
        if h < 0:
            raise ValueError("altura negativa")
        return h
    except Exception as e:
        raise ValueError(f"No se pudo parsear altura más reciente: '{text}' ({e})")

def sample_random_heights(n: int = RANDOM_COUNT_DEFAULT) -> List[int]:
    latest = get_latest_height()
    k = max(1, min(n, latest + 1))
    # Muestra única sin reemplazo sobre el rango [0..latest]
    return sorted(random.sample(range(latest + 1), k=k))

def get_block_header_fields(block_hash: str) -> Dict:
    resp = _request_get(RAWBLOCK_URL.format(block_hash=block_hash), timeout=20)
    resp.raise_for_status()
    rb = resp.json()
    # Blockchain.com field names
    version = rb.get("ver")
    prev_block = rb.get("prev_block")
    merkle_root = rb.get("mrkl_root")
    timestamp = rb.get("time")
    bits_dec = rb.get("bits")           # decimal compact target
    bits_hex = format(bits_dec, "08x") if isinstance(bits_dec, int) else None
    height = rb.get("height")
    # Validaciones suaves (avisos) de hex de 64 chars
    def _is_hex_64(s: str) -> bool:
        if not isinstance(s, str) or len(s) != 64:
            return False
        try:
            int(s, 16)
            return True
        except Exception:
            return False
    if not _is_hex_64(prev_block):
        raise ValueError(f"block {block_hash}: prev_block no es hex de 64 chars")
    if not _is_hex_64(merkle_root):
        raise ValueError(f"block {block_hash}: merkle_root no es hex de 64 chars")
    return {
        "label": f"Block #{height}",
        "height": height,
        "hash": rb.get("hash"),
        "version": version,
        "prev_block": prev_block,
        "merkle_root": merkle_root,
        "timestamp": timestamp,
        "bits_hex": bits_hex,
        "bits": bits_dec,
        "source": f"https://www.blockchain.com/btc/block/{rb.get('hash')}"
    }

def main(heights: List[int]) -> None:
    out: List[Dict] = []
    # Cache local: si existe blocks.json, reutilizar entradas válidas por altura
    cache_by_height: Dict[int, Dict] = {}
    try:
        with open("blocks.json", "r", encoding="utf-8") as f:
            existing = json.load(f)
        if isinstance(existing, list):
            for item in existing:
                try:
                    h = int(item.get("height"))
                    if h not in cache_by_height:
                        cache_by_height[h] = item
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[warn] No se pudo cargar cache local blocks.json: {e}")
    for h in heights:
        try:
            cached = cache_by_height.get(h)
            if cached and all(k in cached for k in ("prev_block", "merkle_root", "version", "timestamp", "bits")):
                out.append(cached)
                print(f"[cache] height={h} hash={cached.get('hash','?')}")
                continue
            bhash = get_block_hash_by_height(h)
            item = get_block_header_fields(bhash)
            out.append(item)
            print(f"[ok] height={h} hash={bhash}")
            time.sleep(0.5)  # be gentle
        except Exception as e:
            print(f"[warn] height={h} -> {e}")
    with open("blocks.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(out)} blocks to blocks.json")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        heights = list(dict.fromkeys([int(x) for x in sys.argv[1:]]))  # de-dupe preserve order
        print(f"Usando alturas proporcionadas por CLI ({len(heights)}): {heights[:5]}{'...' if len(heights)>5 else ''}")
    else:
        try:
            heights = sample_random_heights(RANDOM_COUNT_DEFAULT)
            print(f"Muestreando {len(heights)} alturas aleatorias entre 0 y la última: {heights[:5]}{'...' if len(heights)>5 else ''}")
        except Exception as e:
            print(f"[warn] No se pudo obtener alturas aleatorias ({e}). Usando fallback mínimo [0,1,2]")
            heights = [0, 1, 2]
    main(heights)

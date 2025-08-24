#!/usr/bin/env python3
"""
make_blocks_json.py
Desc: Fetch real Bitcoin block headers for a list of heights and save to blocks.json.
Requires: Python 3.8+, requests
Usage:
  python make_blocks_json.py                # uses default curated heights (20+)
  python make_blocks_json.py 0 1 2 210000  # or pass your own heights
Data sources:
  - Blockchain.com API 'block-height' + 'rawblock' endpoints.
"""
import sys, json, time
from typing import List, Dict
import requests

BLOCK_HEIGHT_URL = "https://blockchain.info/block-height/{height}?format=json"
RAWBLOCK_URL = "https://blockchain.info/rawblock/{block_hash}"

# Default curated set (mix of historical + halving + feature activations)
DEFAULT_HEIGHTS = [
    0, 1, 2, 3, 9, 100000, 123456, 170, 200000, 210000,
    277316, 300000, 420000, 481824, 500000, 508409, 600000, 630000,
    700000, 709632, 800000, 840000
]

def get_block_hash_by_height(height: int) -> str:
    resp = requests.get(BLOCK_HEIGHT_URL.format(height=height), timeout=20)
    resp.raise_for_status()
    data = resp.json()
    # pick the block with matching height (main chain)
    for blk in data.get("blocks", []):
        if blk.get("height") == height:
            return blk["hash"]
    # fallback to first
    return data["blocks"][0]["hash"]

def get_block_header_fields(block_hash: str) -> Dict:
    resp = requests.get(RAWBLOCK_URL.format(block_hash=block_hash), timeout=20)
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
    out = []
    for h in heights:
        try:
            bhash = get_block_hash_by_height(h)
            item = get_block_header_fields(bhash)
            out.append(item)
            print(f"[ok] height={h} hash={bhash}")
            time.sleep(0.2)  # be gentle
        except Exception as e:
            print(f"[warn] height={h} -> {e}")
    with open("blocks.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Saved {len(out)} blocks to blocks.json")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        heights = list(dict.fromkeys([int(x) for x in sys.argv[1:]]))  # de-dupe preserve order
    else:
        heights = DEFAULT_HEIGHTS
    main(heights)

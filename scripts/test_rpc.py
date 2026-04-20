"""Quick test — verify Monad RPC is accessible and returning data."""

import httpx
import json


RPC_URL = "https://rpc.monad.xyz"


def rpc(method, params=[]):
    resp = httpx.post(
        RPC_URL,
        json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
        timeout=10,
    )
    return resp.json()["result"]


def main():
    # 1. Get latest block
    latest_hex = rpc("eth_blockNumber")
    latest = int(latest_hex, 16)
    print(f"✅ Latest block: {latest:,}")

    # 2. Get a recent block with full transactions
    block = rpc("eth_getBlockByNumber", [hex(latest - 5), True])
    block_num = int(block["number"], 16)
    tx_count = len(block["transactions"])
    timestamp = int(block["timestamp"], 16)
    print(f"✅ Block {block_num}: {tx_count} transactions, timestamp {timestamp}")

    # 3. Show first transaction details
    if block["transactions"]:
        tx = block["transactions"][0]
        from_addr = tx.get("from", "?")
        to_addr = tx.get("to", "contract creation")
        value_wei = int(tx.get("value", "0x0"), 16)
        value_mon = value_wei / 1e18
        print(f"\n📝 Sample transaction:")
        print(f"   Hash:  {tx['hash']}")
        print(f"   From:  {from_addr}")
        print(f"   To:    {to_addr}")
        print(f"   Value: {value_mon:.4f} MON")
        print(f"   Input: {tx.get('input', '0x')[:20]}...")

    # 4. Chain info
    chain_id = rpc("eth_chainId")
    print(f"\n🔗 Chain ID: {int(chain_id, 16)} (Monad Mainnet = 143)")

    print("\n✅ All checks passed! RPC is working.")


if __name__ == "__main__":
    main()

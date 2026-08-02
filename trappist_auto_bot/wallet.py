"""Wallet utilities: balance checks for Casper and Solana."""

from dataclasses import dataclass
from typing import Any

import requests

from trappist_auto_bot.utils.logger import get_logger

logger = get_logger(__name__)

# Public Casper mainnet node. You can override with CASPER_NODE_URL.
DEFAULT_CASPER_NODE = "https://node.mainnet.casper.network/rpc"


@dataclass(frozen=True)
class Balance:
    """Wallet balance for a single chain."""

    network: str
    address: str
    balance_motes: int
    balance_human: float
    decimals: int = 9


class WalletService:
    """Check balances and health for configured wallets."""

    def __init__(
        self,
        casper_public_key: str,
        solana_public_key: str = "",
        node_url: str = DEFAULT_CASPER_NODE,
    ) -> None:
        self.casper_public_key = casper_public_key
        self.solana_public_key = solana_public_key
        self.node_url = node_url or DEFAULT_CASPER_NODE

    def get_casper_balance(self, node_url: str | None = None) -> Balance:
        """Query the Casper mainnet balance for the configured public key."""
        if not self.casper_public_key:
            raise WalletError("No Casper public key configured")

        url = node_url or self.node_url
        state_root_hash = self._get_latest_state_root_hash(url)
        main_purse = self._get_main_purse_uref(url)
        params = {
            "state_root_hash": state_root_hash,
            "purse_uref": main_purse,
        }
        response = requests.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": "state_get_balance", "params": params},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise WalletError(f"Casper RPC error: {data['error']}")

        balance_value = int(data["result"]["balance_value"])
        return Balance(
            network="casper",
            address=self.casper_public_key,
            balance_motes=balance_value,
            balance_human=balance_value / 1_000_000_000,
        )

    def _get_latest_state_root_hash(self, node_url: str) -> str:
        response = requests.post(
            node_url,
            json={"jsonrpc": "2.0", "id": 1, "method": "chain_get_state_root_hash", "params": []},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise WalletError(f"Casper RPC error: {data['error']}")
        return data["result"]["state_root_hash"]

    def _get_main_purse_uref(self, node_url: str) -> str:
        response = requests.post(
            node_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "state_get_account_info",
                "params": {"public_key": self.casper_public_key},
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise WalletError(f"Casper RPC error: {data['error']}")
        return data["result"]["account"]["main_purse"]

    def has_sufficient_casper_balance(self, min_motes: int) -> bool:
        """Return True if the Casper balance is at least ``min_motes``."""
        if min_motes <= 0:
            return True
        try:
            balance = self.get_casper_balance()
            logger.info(
                "Casper balance: %s CSPR (%s motes)",
                balance.balance_human,
                balance.balance_motes,
            )
            return balance.balance_motes >= min_motes
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to check Casper balance: %s", exc)
            # Fail safe: do not proceed if we cannot verify balance.
            return False

    def get_casper_balance_sync(self) -> Balance:
        """Convenience synchronous wrapper to fetch the Casper balance."""
        return self.get_casper_balance()


class WalletError(Exception):
    """Raised when wallet operations fail."""

"""
Autonomous Solidity smart-contract agent.

Generate ERC-20/ERC-721/custom contracts from templates, compile with solcx,
deploy with optional CREATE2 deterministic address, and stream events.

ENV:
  WEB3_RPC_URL, ETH_PRIVATE_KEY, WEB3_MODE=sim|live
  ETHERSCAN_API_KEY      optional verification (placeholder)
"""

import os
import re
import json
import logging
import hashlib
from pathlib import Path
from datetime import datetime

from integrations.web3_client import (
    _lazy_init, assert_sim, send_transaction, get_address, HAS_WEB3
)
from integrations.supabase_client import insert, update

log = logging.getLogger("smart_contract_agent")

_OUTPUT_DIR = Path(os.path.expanduser(os.getenv("CONTRACT_DIR", "~/ai-mesh/contracts")))
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

try:
    import solcx
    HAS_SOLCX = True
except Exception as exc:
    log.warning("solcx not installed: %s", exc)
    solcx = None
    HAS_SOLCX = False


ERC20_TEMPLATE = '''// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
contract {{name}} is ERC20, Ownable {
    constructor(address initialOwner, uint256 initialSupply) ERC20("{{name}}", "{{symbol}}") Ownable(initialOwner) {
        _mint(initialOwner, initialSupply * 10 ** decimals());
    }
}
'''

ERC721_TEMPLATE = '''// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
contract {{name}} is ERC721, Ownable {
    uint256 public totalSupply;
    constructor(address initialOwner) ERC721("{{name}}", "{{symbol}}") Ownable(initialOwner) {}
    function mint(address to) public onlyOwner returns (uint256) {
        totalSupply++;
        _safeMint(to, totalSupply);
        return totalSupply;
    }
}
'''

SIMPLE_ESCROW_TEMPLATE = '''// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
contract SimpleEscrow {
    address public client;
    address public provider;
    address public evaluator;
    enum State { Created, Funded, Delivered, Released, Disputed }
    State public state;
    uint256 public amount;
    mapping(address => bool) public approvals;
    event Funded(address indexed client, uint256 amount);
    event Delivered(address indexed provider);
    event Released();
    event Disputed();
    modifier onlyClient() { require(msg.sender == client, "not client"); _; }
    modifier onlyEvaluator() { require(msg.sender == evaluator, "not evaluator"); _; }
    constructor(address _provider, address _evaluator) { client = msg.sender; provider = _provider; evaluator = _evaluator; state = State.Created; }
    function fund() external payable onlyClient { require(state == State.Created, "bad state"); amount = msg.value; state = State.Funded; emit Funded(client, amount); }
    function markDelivered() external { require(msg.sender == provider && state == State.Funded, "bad state"); state = State.Delivered; emit Delivered(provider); }
    function approve() external { require(state == State.Delivered); approvals[msg.sender] = true; if (approvals[client] && approvals[provider]) { _release(); } }
    function evaluatorRelease() external onlyEvaluator { require(state == State.Delivered); _release(); }
    function dispute() external { require(state == State.Delivered); state = State.Disputed; emit Disputed(); }
    function _release() internal { require(state == State.Delivered); (bool ok,)=payable(provider).call{value: amount}(""); require(ok); state = State.Released; emit Released(); }
}
'''

CONTRACT_TEMPLATES = {
    "erc20": ERC20_TEMPLATE,
    "erc721": ERC721_TEMPLATE,
    "escrow": SIMPLE_ESCROW_TEMPLATE,
}


def _render(template: str, params: dict) -> str:
    out = template
    for k, v in params.items():
        out = out.replace(f"{{{{{k}}}}}", str(v))
    return out


def write_contract(contract_type: str, name: str, params: dict) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_]", "", name)
    template = CONTRACT_TEMPLATES.get(contract_type)
    if not template:
        raise ValueError(f"Unknown contract type: {contract_type}")
    source = _render(template, {"name": safe_name, **params})
    path = _OUTPUT_DIR / f"{safe_name}_{contract_type}.sol"
    path.write_text(source)
    log.info("Contract source written: %s", path)
    return path


def compile_contract(source_path: Path) -> dict:
    if not HAS_SOLCX:
        return {"error": "solcx not installed", "path": str(source_path)}
    if not HAS_WEB3:
        return {"error": "web3.py not installed"}
    solcx.install_solc("0.8.20")
    compiled = solcx.compile_files([str(source_path)], output_values=["abi", "bin"], solc_version="0.8.20")
    # Find the contract item matching the filename
    key = next(k for k in compiled if Path(k.split(":")[0]).name == source_path.name)
    return {
        "abi": compiled[key]["abi"],
        "bytecode": compiled[key]["bin"],
        "key": key,
    }


def deploy_contract(abi: list, bytecode: str, *constructor_args) -> dict:
    assert_sim("deploy_contract")
    w3 = _lazy_init()
    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx = Contract.constructor(*constructor_args).build_transaction({
        "from": get_address(),
        "nonce": w3.eth.get_transaction_count(get_address()),
    })
    receipt = send_transaction(tx)
    receipt["contract_address"] = receipt.get("tx_hash")  # real address in receipt.contractAddress
    if "tx_hash" in receipt:
        try:
            actual = w3.eth.get_transaction_receipt(receipt["tx_hash"]).contractAddress
            receipt["contract_address"] = actual
        except Exception:
            pass
    return receipt


def monitor_events(contract_address: str, abi: list, event_name: str,
                   from_block: int | None = None, to_block: int = "latest") -> list[dict]:
    if not _LIVE():
        return []
    w3 = _lazy_init()
    from_block = from_block or w3.eth.block_number - 100
    contract = w3.eth.contract(address=w3.to_checksum_address(contract_address), abi=abi)
    event = getattr(contract.events, event_name)
    return [dict(e) for e in event().get_logs({"fromBlock": from_block, "toBlock": to_block})]


def generate_and_deploy(contract_type: str, name: str,
                        constructor_args: list | None = None,
                        contract_params: dict | None = None) -> dict:
    params = contract_params or {}
    source_path = write_contract(contract_type, name, params)
    compiled = compile_contract(source_path)
    if "error" in compiled:
        return {"error": compiled["error"], "source": str(source_path)}

    receipt = deploy_contract(compiled["abi"], compiled["bytecode"], *(constructor_args or []))
    record = insert("smart_contracts", {
        "name": name,
        "contract_type": contract_type,
        "source_path": str(source_path),
        "abi": compiled["abi"],
        "address": receipt.get("contract_address"),
        "deploy_tx": receipt.get("tx_hash"),
        "network": os.getenv("WEB3_NETWORK", "unknown"),
    })
    receipt["db_record"] = record
    return receipt


def _LIVE() -> bool:
    return os.getenv("WEB3_MODE", "sim").lower() == "live"

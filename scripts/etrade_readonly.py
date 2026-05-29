#!/usr/bin/env python3
"""Read-only E*TRADE OAuth/account smoke test.

This script performs the manual OAuth 1.0a flow, then lists accounts and
portfolio positions. It never places, previews, modifies, or cancels orders.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import argparse
import json
import os
import secrets
import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Tuple
from urllib.parse import parse_qsl, quote, urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
TARGETS_FILE = ROOT / "config" / "portfolio_targets.json"
DATA_DIR = ROOT / "data"
DB_FILE = DATA_DIR / "stock_trading.sqlite"

REQUEST_TOKEN_URL = "https://api.etrade.com/oauth/request_token"
AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize"
ACCESS_TOKEN_URL = "https://api.etrade.com/oauth/access_token"


def load_env(path: Path) -> None:
    if not path.exists():
        raise SystemExit(
            f"Missing {path}. Copy .env.example to .env and add your E*TRADE keys."
        )

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def pct_encode(value: object) -> str:
    return quote(str(value), safe="~")


def oauth_base_params(consumer_key: str, token: str | None = None) -> Dict[str, str]:
    params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_version": "1.0",
    }
    if token:
        params["oauth_token"] = token
    return params


def sign(
    method: str,
    url: str,
    params: Mapping[str, object],
    consumer_secret: str,
    token_secret: str = "",
) -> str:
    normalized = "&".join(
        f"{pct_encode(key)}={pct_encode(value)}" for key, value in sorted(params.items())
    )
    base = "&".join([method.upper(), pct_encode(url), pct_encode(normalized)])
    key = f"{pct_encode(consumer_secret)}&{pct_encode(token_secret)}"
    digest = hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def auth_header(params: Mapping[str, object]) -> str:
    pieces = ", ".join(
        f'{pct_encode(key)}="{pct_encode(value)}"'
        for key, value in sorted(params.items())
        if key.startswith("oauth_")
    )
    return f"OAuth {pieces}"


def request_oauth_token(
    url: str,
    consumer_key: str,
    consumer_secret: str,
    token: str | None = None,
    token_secret: str = "",
    extra_params: Mapping[str, str] | None = None,
) -> Dict[str, str]:
    params = oauth_base_params(consumer_key, token)
    if extra_params:
        params.update(extra_params)
    params["oauth_signature"] = sign("GET", url, params, consumer_secret, token_secret)

    request = Request(url, headers={"Authorization": auth_header(params)})
    with urlopen(request, timeout=30) as response:
        body = response.read().decode()
    return dict(parse_qsl(body))


def api_get(
    url: str,
    consumer_key: str,
    consumer_secret: str,
    access_token: str,
    access_secret: str,
    query: Mapping[str, object] | None = None,
) -> object:
    query = query or {}
    oauth_params = oauth_base_params(consumer_key, access_token)
    signature_params = {**oauth_params, **query}
    oauth_params["oauth_signature"] = sign(
        "GET", url, signature_params, consumer_secret, access_secret
    )

    full_url = url
    if query:
        full_url = f"{url}?{urlencode(query)}"

    request = Request(
        full_url,
        headers={
            "Authorization": auth_header(oauth_params),
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def environment_base() -> str:
    env = os.environ.get("ETRADE_ENV", "sandbox").strip().lower()
    if env in {"prod", "production", "live"}:
        return "https://api.etrade.com/v1"
    if env == "sandbox":
        return "https://apisb.etrade.com/v1"
    raise SystemExit("ETRADE_ENV must be sandbox or production")


def iter_accounts(payload: object) -> Iterable[Mapping[str, object]]:
    if not isinstance(payload, dict):
        return []
    response = payload.get("AccountListResponse", payload)
    accounts = response.get("Accounts", {}) if isinstance(response, dict) else {}
    account = accounts.get("Account", []) if isinstance(accounts, dict) else []
    if isinstance(account, dict):
        return [account]
    if isinstance(account, list):
        return account
    return []


def iter_positions(payload: object) -> Iterable[Mapping[str, object]]:
    if not isinstance(payload, dict):
        return []
    response = payload.get("PortfolioResponse", payload)
    portfolios = response.get("AccountPortfolio", []) if isinstance(response, dict) else []
    if isinstance(portfolios, dict):
        portfolios = [portfolios]

    positions: List[Mapping[str, object]] = []
    for portfolio in portfolios:
        if not isinstance(portfolio, dict):
            continue
        raw_positions = portfolio.get("Position", [])
        if isinstance(raw_positions, dict):
            positions.append(raw_positions)
        elif isinstance(raw_positions, list):
            positions.extend(item for item in raw_positions if isinstance(item, dict))
    return positions


def money(value: object) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "-"


def number(value: object) -> str:
    try:
        return f"{float(value):,.4g}"
    except (TypeError, ValueError):
        return "-"


def percent(value: object) -> str:
    try:
        return f"{float(value):,.2f}%"
    except (TypeError, ValueError):
        return "-"


def load_targets() -> Mapping[str, object]:
    if not TARGETS_FILE.exists():
        return {}
    return json.loads(TARGETS_FILE.read_text())


def choose_account(
    accounts: List[Mapping[str, object]],
    environment: str,
    targets: Mapping[str, object],
) -> Mapping[str, object]:
    if len(accounts) == 1:
        return accounts[0]

    sync_config = targets.get("etrade_sync", {})
    if isinstance(sync_config, dict) and environment in {"production", "prod", "live"}:
        default_account_type = sync_config.get("default_production_account_type")
        if default_account_type:
            matches = [
                account
                for account in accounts
                if str(account.get("accountType", "")).upper()
                == str(default_account_type).upper()
            ]
            if len(matches) == 1:
                print(
                    "\nAuto-selected production account "
                    f"{matches[0].get('accountType')} / "
                    f"{matches[0].get('institutionType', 'UNKNOWN')}"
                )
                return matches[0]
            if len(matches) > 1:
                print(
                    "\nMultiple production accounts match "
                    f"{default_account_type}; please select one."
                )
            else:
                print(
                    "\nNo production account matched "
                    f"{default_account_type}; please select one."
                )

    print("\nSelect an account number to fetch portfolio positions.")
    selection = input("Press Enter for account 1: ").strip()
    if not selection:
        return accounts[0]

    try:
        index = int(selection)
    except ValueError:
        raise SystemExit("Account selection must be a number.")

    if index < 1 or index > len(accounts):
        raise SystemExit(f"Account selection must be between 1 and {len(accounts)}.")
    return accounts[index - 1]


def print_holdings(positions: Iterable[Mapping[str, object]]) -> None:
    rows = []
    for position in positions:
        product = position.get("Product", {})
        complete = position.get("Complete", {})
        symbol = position.get("symbolDescription")
        if isinstance(product, dict):
            symbol = product.get("symbol") or symbol
        rows.append(
            [
                str(symbol or "-"),
                number(position.get("quantity")),
                money(complete.get("lastTrade") if isinstance(complete, dict) else None),
                money(position.get("marketValue")),
                money(position.get("pricePaid")),
                money(position.get("totalGain")),
                percent(position.get("totalGainPct")),
                percent(position.get("pctOfPortfolio")),
            ]
        )

    if not rows:
        print("\nNo positions returned for this account.")
        return

    headers = [
        "Symbol",
        "Qty",
        "Last",
        "Market Value",
        "Price Paid",
        "Total Gain",
        "Gain %",
        "Portfolio %",
    ]
    widths = [
        max(len(str(row[index])) for row in [headers] + rows)
        for index in range(len(headers))
    ]

    print("\nHoldings:")
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def to_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def init_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS etrade_sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            environment TEXT NOT NULL,
            account_id_key TEXT NOT NULL,
            account_type TEXT,
            institution_type TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS etrade_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            security_type TEXT,
            quantity REAL,
            last_price REAL,
            market_value REAL,
            price_paid REAL,
            total_gain REAL,
            total_gain_pct REAL,
            pct_of_portfolio REAL,
            position_type TEXT,
            raw_json TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES etrade_sync_runs(id)
        )
        """
    )
    return conn


def save_snapshot(
    selected_account: Mapping[str, object],
    positions: Iterable[Mapping[str, object]],
) -> int:
    env = os.environ.get("ETRADE_ENV", "sandbox").strip().lower()
    conn = init_db()
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO etrade_sync_runs (
                environment,
                account_id_key,
                account_type,
                institution_type
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                env,
                selected_account.get("accountIdKey"),
                selected_account.get("accountType"),
                selected_account.get("institutionType"),
            ),
        )
        run_id = int(cursor.lastrowid)

        for position in positions:
            product = position.get("Product", {})
            complete = position.get("Complete", {})
            if not isinstance(product, dict):
                product = {}
            if not isinstance(complete, dict):
                complete = {}

            symbol = product.get("symbol") or position.get("symbolDescription")
            conn.execute(
                """
                INSERT INTO etrade_positions (
                    run_id,
                    symbol,
                    security_type,
                    quantity,
                    last_price,
                    market_value,
                    price_paid,
                    total_gain,
                    total_gain_pct,
                    pct_of_portfolio,
                    position_type,
                    raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    symbol,
                    product.get("securityType"),
                    to_float(position.get("quantity")),
                    to_float(complete.get("lastTrade")),
                    to_float(position.get("marketValue")),
                    to_float(position.get("pricePaid")),
                    to_float(position.get("totalGain")),
                    to_float(position.get("totalGainPct")),
                    to_float(position.get("pctOfPortfolio")),
                    position.get("positionType"),
                    json.dumps(position, sort_keys=True),
                ),
            )
    conn.close()
    return run_id


def etrade_credentials() -> Tuple[str, str]:
    env = os.environ.get("ETRADE_ENV", "sandbox").strip().lower()
    if env == "sandbox":
        key = os.environ.get("ETRADE_SANDBOX_API") or os.environ.get(
            "ETRADE_CONSUMER_KEY"
        )
        secret = os.environ.get("ETRADE_SANDBOX_SECRET") or os.environ.get(
            "ETRADE_CONSUMER_SECRET"
        )
    elif env in {"prod", "production", "live"}:
        key = os.environ.get("ETRADE_PROD_API") or os.environ.get("ETRADE_CONSUMER_KEY")
        secret = os.environ.get("ETRADE_PROD_SECRET") or os.environ.get(
            "ETRADE_CONSUMER_SECRET"
        )
    else:
        raise SystemExit("ETRADE_ENV must be sandbox or production")

    if not key or not secret:
        raise SystemExit(
            "Missing E*TRADE credentials. For sandbox, set ETRADE_SANDBOX_API "
            "and ETRADE_SANDBOX_SECRET in .env."
        )
    return key, secret


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only E*TRADE account and portfolio sync."
    )
    parser.add_argument(
        "--env",
        choices=["sandbox", "production"],
        default=os.environ.get("ETRADE_ENV", "sandbox").strip().lower(),
        help="E*TRADE environment to use. Defaults to ETRADE_ENV or sandbox.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.environ["ETRADE_ENV"] = args.env
    load_env(ENV_FILE)
    targets = load_targets()
    consumer_key, consumer_secret = etrade_credentials()
    env = os.environ.get("ETRADE_ENV", "sandbox").strip().lower()
    print(f"Using E*TRADE {env} environment in read-only mode.")

    token_response = request_oauth_token(
        REQUEST_TOKEN_URL,
        consumer_key,
        consumer_secret,
        extra_params={"oauth_callback": "oob"},
    )
    request_token = token_response["oauth_token"]
    request_secret = token_response["oauth_token_secret"]

    print("\nAuthorize this app with E*TRADE:")
    print(f"{AUTHORIZE_URL}?key={pct_encode(consumer_key)}&token={pct_encode(request_token)}")
    verifier = input("\nPaste the verifier code here: ").strip()
    if not verifier:
        raise SystemExit("No verifier provided.")

    access_response = request_oauth_token(
        ACCESS_TOKEN_URL,
        consumer_key,
        consumer_secret,
        token=request_token,
        token_secret=request_secret,
        extra_params={"oauth_verifier": verifier},
    )
    access_token = access_response["oauth_token"]
    access_secret = access_response["oauth_token_secret"]

    base = environment_base()
    accounts_payload = api_get(
        f"{base}/accounts/list",
        consumer_key,
        consumer_secret,
        access_token,
        access_secret,
    )
    accounts = list(iter_accounts(accounts_payload))

    print("\nAccounts:")
    for index, account in enumerate(accounts, start=1):
        account_id_key = account.get("accountIdKey")
        account_type = account.get("accountType", "UNKNOWN")
        institution_type = account.get("institutionType", "UNKNOWN")
        print(f"{index}. {account_type} / {institution_type} / accountIdKey={account_id_key}")

    if not accounts:
        print("\nNo accounts returned.")
        return 0

    selected = choose_account(accounts, env, targets)
    account_id_key = selected.get("accountIdKey")
    if not account_id_key:
        print("\nSelected account did not include accountIdKey; cannot fetch portfolio.")
        return 0

    portfolio_payload = api_get(
        f"{base}/accounts/{account_id_key}/portfolio",
        consumer_key,
        consumer_secret,
        access_token,
        access_secret,
        query={"view": "COMPLETE"},
    )
    positions = list(iter_positions(portfolio_payload))
    print_holdings(positions)
    run_id = save_snapshot(selected, positions)
    print(f"\nSaved snapshot run {run_id} to {DB_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

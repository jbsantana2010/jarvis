"""budget_analyzer.py — Voice-friendly budget analysis for JARVIS.

All public functions are synchronous (called from async executors via
asyncio.to_thread). They return (success: bool, message: str) tuples
where message is a concise, spoken-English response.

Financial data is read strictly from local files. No hallucination of
interest rates, balances, or payments. If data is missing, the response
says so clearly.
"""

import asyncio
import logging
from typing import Optional

import budget_reader

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #

def _dollars(amount: Optional[float]) -> str:
    if amount is None:
        return "unknown amount"
    return f"${amount:,.2f}"


def _pct_str(pct: Optional[float]) -> str:
    if pct is None:
        return "unknown rate"
    return f"{pct:.2f}%"


def _clean_status(status: Optional[str]) -> str:
    """Strip emoji from status strings for cleaner speech."""
    if not status:
        return ""
    # Remove common emoji
    for emoji in ["🔴", "🟠", "🟡", "🟢", "✅", "⚠", "⚡"]:
        status = status.replace(emoji, "").strip()
    return status.strip()


# --------------------------------------------------------------------------- #
# Core analysis
# --------------------------------------------------------------------------- #

def _load_debts():
    """Load debts with error handling."""
    return budget_reader.read_debts()


def _load_snapshot():
    return budget_reader.read_snapshot()


def _load_calendar():
    return budget_reader.read_calendar()


def _debit_debts(data: dict) -> list:
    """Return only real debt entries (not summary rows, non-zero balance)."""
    return [d for d in data.get("debts", []) if d.get("balance") is not None]


# --------------------------------------------------------------------------- #
# Public summary functions
# All return (bool, str)
# --------------------------------------------------------------------------- #

def budget_summary() -> tuple[bool, str]:
    """Full financial snapshot: income, expenses, total debt, cash flow."""
    snap = _load_snapshot()
    if not snap["ok"]:
        return False, f"I couldn't read your budget file, sir. {snap['error']}"

    income = snap["monthly_income"]
    expenses = snap["total_expenses"]
    net = snap["net_cash_flow"]
    total_debt = snap["total_debt"]
    monthly_int = snap["monthly_interest"]
    dti = snap["debt_to_income"]

    parts = []

    if income is not None:
        parts.append(f"Your monthly take-home is {_dollars(income)}.")

    if expenses is not None:
        parts.append(f"Total monthly outflow is {_dollars(expenses)}.")

    if net is not None:
        if net < 0:
            parts.append(f"You are currently running a deficit of {_dollars(abs(net))} per month.")
        else:
            parts.append(f"You have a monthly surplus of {_dollars(net)}.")

    if total_debt is not None:
        parts.append(f"Total outstanding debt is {_dollars(total_debt)}.")

    if monthly_int is not None:
        parts.append(f"You are burning {_dollars(monthly_int)} in interest charges every month.")

    if dti is not None:
        dti_pct = round(dti * 100, 1)
        parts.append(f"Your debt-to-income ratio is {dti_pct}%.")
        if dti > 0.5:
            parts.append("That is above the recommended 50% threshold — aggressive paydown is the priority.")

    if not parts:
        return False, "Your budget file was found but I could not read the summary values, sir."

    parts.append("Say 'show my debts' for the full debt breakdown, or 'give me a payoff plan' for strategy.")
    return True, " ".join(parts)


def total_debt() -> tuple[bool, str]:
    """Speak total debt figure with quick breakdown of top balances."""
    data = _load_debts()
    if not data["ok"]:
        return False, f"I couldn't read your debt data, sir. {data['error']}"

    debts = _debit_debts(data)
    if not debts:
        return False, "No debt entries found in your budget file, sir."

    total = data.get("total_debt")
    if total is None:
        total = sum(d["balance"] for d in debts if d["balance"])

    msg = f"Your total debt is {_dollars(total)}, spread across {len(debts)} accounts."

    # Top 3 by balance
    by_balance = sorted(debts, key=lambda d: d["balance"] or 0, reverse=True)[:3]
    top_names = ", ".join(f"{d['name']} at {_dollars(d['balance'])}" for d in by_balance)
    msg += f" Largest balances: {top_names}."

    min_total = data.get("total_min_payments")
    if min_total:
        msg += f" Minimum payments total {_dollars(min_total)} per month."

    return True, msg


def show_debts() -> tuple[bool, str]:
    """List all debts with balance, APR, and current priority status."""
    data = _load_debts()
    if not data["ok"]:
        return False, f"I couldn't read your debt data, sir. {data['error']}"

    debts = _debit_debts(data)
    if not debts:
        return False, "No debt entries found in your budget file, sir."

    # Sort by priority if available, else by APR descending
    debts_sorted = sorted(debts, key=lambda d: d.get("priority") or 99)

    lines = []
    for d in debts_sorted:
        name = d["name"]
        bal = _dollars(d["balance"])
        apr = _pct_str(d["apr_pct"])
        min_p = f"minimum {_dollars(d['min_payment'])}" if d["min_payment"] else ""
        status = _clean_status(d.get("status"))
        line = f"{name}: {bal} at {apr}"
        if min_p:
            line += f", {min_p}"
        if status:
            line += f" — {status}"
        lines.append(line)

    total = data.get("total_debt")
    header = f"You have {len(debts)} debts totalling {_dollars(total)}. "
    return True, header + ". ".join(lines) + "."


def payoff_plan() -> tuple[bool, str]:
    """Recommend avalanche or snowball payoff order with reasoning."""
    data = _load_debts()
    if not data["ok"]:
        return False, f"I couldn't read your debt data, sir. {data['error']}"

    debts = _debit_debts(data)
    if not debts:
        return False, "No debt entries found in your budget file, sir."

    # Check whether APR data is available
    debts_with_apr = [d for d in debts if d.get("apr_pct") is not None and d["apr_pct"] > 0]

    if debts_with_apr:
        # Avalanche — highest APR first
        ordered = sorted(debts_with_apr, key=lambda d: d["apr_pct"], reverse=True)
        strategy = "avalanche method — targeting highest interest rate first to minimize total interest paid"

        # Also flag any 0% APR debts to knock out immediately (free minimum payments)
        zero_apr = [d for d in debts if d.get("apr_pct") is not None and d["apr_pct"] == 0 and d.get("balance", 0) > 0]
        special_notes = []
        if zero_apr:
            names = " and ".join(d["name"] for d in zero_apr)
            special_notes.append(f"Pay off {names} immediately — zero percent APR and small balance frees up cash.")

        # Flag any past-due debts from notes
        past_due = [d for d in debts if d.get("notes") and "PAST DUE" in (d["notes"] or "").upper()]
        for pd in past_due:
            special_notes.append(f"Catch up {pd['name']} — it is past due.")

        intro = f"I recommend the {strategy}. "
        if special_notes:
            intro += " ".join(special_notes) + " Then: "
        else:
            intro += "Attack in this order: "

        steps = []
        for i, d in enumerate(ordered[:5], 1):
            bal = _dollars(d["balance"])
            apr = _pct_str(d["apr_pct"])
            steps.append(f"Number {i}: {d['name']} — {bal} at {apr}")

        if len(ordered) > 5:
            steps.append(f"...and {len(ordered) - 5} more. Say 'show my debts' for the full list.")

        return True, intro + ". ".join(steps) + ". Each time you pay one off, roll that minimum payment into the next target."

    else:
        # Snowball — smallest balance first (no APR data)
        ordered = sorted(debts, key=lambda d: d.get("balance") or 999999)
        strategy = "snowball method — targeting smallest balance first since interest rate data is not available"

        intro = f"Using the {strategy}. Attack in this order: "
        steps = [f"{d['name']} at {_dollars(d['balance'])}" for d in ordered[:5]]
        return True, intro + ", then ".join(steps) + "."


def highest_interest() -> tuple[bool, str]:
    """Name the debt with the highest APR."""
    data = _load_debts()
    if not data["ok"]:
        return False, f"I couldn't read your debt data, sir. {data['error']}"

    debts = _debit_debts(data)
    debts_with_apr = [d for d in debts if d.get("apr_pct") is not None]

    if not debts_with_apr:
        return False, "I found debt entries but no interest rate data in your budget file, sir."

    top = max(debts_with_apr, key=lambda d: d["apr_pct"])
    msg = (
        f"Your highest interest debt is {top['name']} at {_pct_str(top['apr_pct'])} APR "
        f"with a balance of {_dollars(top['balance'])}."
    )
    if top.get("monthly_interest"):
        msg += f" That is costing you {_dollars(top['monthly_interest'])} in interest every month."
    msg += " This should be your primary attack target."
    return True, msg


def monthly_due() -> tuple[bool, str]:
    """Total minimum payments due this month with a breakdown by due date."""
    data = _load_debts()
    if not data["ok"]:
        return False, f"I couldn't read your debt data, sir. {data['error']}"

    total_min = data.get("total_min_payments")
    debts = _debit_debts(data)

    # Try calendar sheet for due-date breakdown
    cal = _load_calendar()

    if cal["ok"] and cal["payments"]:
        debt_payments = [
            p for p in cal["payments"]
            if "Debt" in (p.get("category") or "")
            and p.get("amount") is not None
            and str(p.get("due_date", "")).rstrip("stndrh").strip().isdigit()
        ]
        total_cal = sum(p["amount"] for p in debt_payments if p.get("amount"))

        if debt_payments:
            # Group by early/mid/late month
            early = [p for p in debt_payments if _due_date_num(p["due_date"]) <= 10]
            mid = [p for p in debt_payments if 10 < _due_date_num(p["due_date"]) <= 20]
            late = [p for p in debt_payments if _due_date_num(p["due_date"]) > 20]

            parts = [f"Your total debt minimums are {_dollars(total_min or total_cal)} per month."]
            if early:
                names = ", ".join(f"{p['name']} {_dollars(p['amount'])}" for p in early)
                parts.append(f"Due in the first 10 days: {names}.")
            if mid:
                names = ", ".join(f"{p['name']} {_dollars(p['amount'])}" for p in mid)
                parts.append(f"Due mid-month: {names}.")
            if late:
                names = ", ".join(f"{p['name']} {_dollars(p['amount'])}" for p in late)
                parts.append(f"Due in the last 10 days: {names}.")
            return True, " ".join(parts)

    # Fallback: just total from Debts sheet
    if total_min:
        debt_count = len(debts)
        return True, f"Your total monthly minimum debt payments are {_dollars(total_min)} across {debt_count} accounts. Say 'show my debts' for a full breakdown."

    return False, "I could not find monthly payment data in your budget file, sir."


def _due_date_num(due_str: str) -> int:
    """Extract a sortable day number from strings like '1st', '12th', '21st'."""
    import re
    m = re.search(r"(\d+)", str(due_str))
    return int(m.group(1)) if m else 99


# --------------------------------------------------------------------------- #
# Async wrappers for server.py
# --------------------------------------------------------------------------- #

async def async_budget_summary() -> tuple[bool, str]:
    return await asyncio.get_event_loop().run_in_executor(None, budget_summary)

async def async_total_debt() -> tuple[bool, str]:
    return await asyncio.get_event_loop().run_in_executor(None, total_debt)

async def async_show_debts() -> tuple[bool, str]:
    return await asyncio.get_event_loop().run_in_executor(None, show_debts)

async def async_payoff_plan() -> tuple[bool, str]:
    return await asyncio.get_event_loop().run_in_executor(None, payoff_plan)

async def async_highest_interest() -> tuple[bool, str]:
    return await asyncio.get_event_loop().run_in_executor(None, highest_interest)

async def async_monthly_due() -> tuple[bool, str]:
    return await asyncio.get_event_loop().run_in_executor(None, monthly_due)

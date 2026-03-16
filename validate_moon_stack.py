#!/usr/bin/env python3
"""
validate_moon_stack.py
Validação end-to-end do Moon-Stack

Executar:
    python3 validate_moon_stack.py
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

print("=" * 60)
print("  🌕 MOON-STACK VALIDATION")
print("=" * 60)
print()

# ─────────────────────────────────────────────────────────────
#  1. Test Browser Daemon
# ─────────────────────────────────────────────────────────────

print("[1/6] Testing Browser Daemon...")

import os
state_file = ROOT / ".gstack" / "browse.json"
if state_file.exists():
    import json
    state = json.loads(state_file.read_text())
    print(f"  ✓ Daemon state: PID={state.get('pid')}, Port={state.get('port')}")
else:
    print("  ⚠ Daemon not running (start with: bash skills/moon_browse/start_daemon.sh &)")

# ─────────────────────────────────────────────────────────────
#  2. Test Browser Bridge
# ─────────────────────────────────────────────────────────────

print("\n[2/6] Testing Browser Bridge...")

async def test_bridge():
    try:
        from core.browser_bridge import BrowserBridge
        bridge = BrowserBridge()
        
        result = await bridge.goto("https://httpbin.org/get")
        status = "✓" if "BROWSER_ERROR" not in result else "✗"
        print(f"  {status} goto: {result[:50]}...")
        
        snap = await bridge.snapshot()
        status = "✓" if len(snap) > 10 else "✗"
        print(f"  {status} snapshot: {len(snap)} chars")
        
        await bridge.close()
        return True
    except Exception as e:
        print(f"  ✗ Bridge error: {e}")
        return False

bridge_ok = asyncio.run(test_bridge())

# ─────────────────────────────────────────────────────────────
#  3. Test Plan Agent
# ─────────────────────────────────────────────────────────────

print("\n[3/6] Testing Plan Agent (CEO mode)...")

async def test_plan():
    try:
        from agents.moon_plan_agent import MoonPlanAgent
        plan = MoonPlanAgent()
        await plan.initialize()
        
        result = await plan.execute("ceo Testar análise estratégica rápida")
        status = "✓" if result.success else "✗"
        print(f"  {status} CEO analysis: {result.data.get('file', 'N/A')}")
        
        await plan.shutdown()
        return result.success
    except Exception as e:
        print(f"  ✗ Plan error: {e}")
        return False

plan_ok = asyncio.run(test_plan())

# ─────────────────────────────────────────────────────────────
#  4. Test Review Agent
# ─────────────────────────────────────────────────────────────

print("\n[4/6] Testing Review Agent...")

async def test_review():
    try:
        from agents.moon_review_agent import MoonReviewAgent
        review = MoonReviewAgent()
        await review.initialize()
        
        result = await review.execute("auto")
        status = "✓" if result.success else "✗"
        health = result.data.get("health_score", "N/A") if result.success else "N/A"
        print(f"  {status} Review: health_score={health}")
        
        await review.shutdown()
        return result.success
    except Exception as e:
        print(f"  ✗ Review error: {e}")
        return False

review_ok = asyncio.run(test_review())

# ─────────────────────────────────────────────────────────────
#  5. Check QA Agent
# ─────────────────────────────────────────────────────────────

print("\n[5/6] Checking QA Agent...")

try:
    from agents.moon_qa_agent import MoonQAAgent
    print("  ✓ MoonQAAgent imported successfully")
    qa_ok = True
except ImportError as e:
    print(f"  ✗ QA import error: {e}")
    qa_ok = False

# ─────────────────────────────────────────────────────────────
#  6. Check Ship Agent
# ─────────────────────────────────────────────────────────────

print("\n[6/6] Checking Ship Agent...")

try:
    from agents.moon_ship_agent import MoonShipAgent
    print("  ✓ MoonShipAgent imported successfully")
    ship_ok = True
except ImportError as e:
    print(f"  ✗ Ship import error: {e}")
    ship_ok = False

# ─────────────────────────────────────────────────────────────
#  Summary
# ─────────────────────────────────────────────────────────────

print()
print("=" * 60)
print("  VALIDATION SUMMARY")
print("=" * 60)
print()

results = {
    "Browser Daemon": state_file.exists(),
    "Browser Bridge": bridge_ok,
    "Plan Agent": plan_ok,
    "Review Agent": review_ok,
    "QA Agent": qa_ok,
    "Ship Agent": ship_ok,
}

for name, ok in results.items():
    status = "✅" if ok else "⚠️"
    print(f"  {status} {name}")

print()
passed = sum(1 for v in results.values() if v)
total = len(results)
print(f"  Result: {passed}/{total} components validated")
print()

if passed >= 5:
    print("  🎉 Moon-Stack is operational!")
else:
    print("  ⚠️  Some components need attention")

print()
print("=" * 60)

sys.exit(0 if passed >= 5 else 1)

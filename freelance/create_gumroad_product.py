#!/usr/bin/env python3
"""
Create the Gumroad product via API.
Run: python3 create_gumroad_product.py
Set GUMROAD_ACCESS_TOKEN in your environment first.
Get token from: https://app.gumroad.com/settings/advanced
"""
import os
import requests

TOKEN = os.getenv("GUMROAD_ACCESS_TOKEN")
if not TOKEN:
    print("ERROR: Set GUMROAD_ACCESS_TOKEN environment variable first.")
    print("  export GUMROAD_ACCESS_TOKEN=your_token_here")
    print("  Get it from: https://app.gumroad.com/settings/advanced -> Access token")
    exit(1)

DESCRIPTION = """
Most tutorials assume you have a server.

I don't. I have an Android phone, Termux, and a 250MB memory limit.

This guide shows you how to run 13 independent Python agents simultaneously on
your Android phone using Termux — within a 250MB memory budget. No server required.
No cloud bill. No monthly fees.

**What you get:**
- Complete Termux setup guide (proot-debian, Python 3, PM2)
- Memory-optimised agent template (runs under 20MB each)
- PM2 ecosystem config for managing 13+ processes
- SQLite database schema for multi-agent coordination
- Flask dashboard for real-time monitoring
- Bash deploy/repair/restart scripts
- Working example: geosignal agent with live ISS position + Kp solar index

**What you need:**
- Android phone (4GB RAM recommended, 2GB minimum)
- Termux from F-Droid (free)
- Basic Python knowledge

**No cloud accounts. No credit card for servers. Runs offline.**
"""

payload = {
    "access_token": TOKEN,
    "name": "13 Agents on a Phone: Multi-Agent Python on Android",
    "price": 2900,          # $29.00 AUD in cents
    "currency": "aud",
    "description": DESCRIPTION,
    "url": "https://samhiotis.com",
    "published": True,
}

print("Creating Gumroad product...")
r = requests.post("https://api.gumroad.com/v2/products", data=payload)

if r.status_code == 201:
    data = r.json()
    product = data.get("product", {})
    print(f"\nSUCCESS!")
    print(f"  Name:       {product.get('name')}")
    print(f"  Product ID: {product.get('id')}")
    print(f"  Short URL:  {product.get('short_url')}")
    print(f"  Price:      ${product.get('formatted_price')}")
    print(f"\nProduct is LIVE at: {product.get('short_url')}")
    print(f"\nNext: Upload a PDF guide to this product in your Gumroad dashboard.")
    print(f"      Even 5 pages covering the basics is enough to start selling.")
    print(f"\nProduct ID to paste into fm_micro_charge.py: {product.get('id')}")
else:
    print(f"\nFAILED: HTTP {r.status_code}")
    print(r.text)
    print("\nCheck your token at https://app.gumroad.com/settings/advanced")

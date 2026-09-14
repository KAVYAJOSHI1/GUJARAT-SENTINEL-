#!/usr/bin/env python3
import os
import sys
import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3000"

def test_recording_flow():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--window-size=1920,1080"]
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            color_scheme="dark"
        )
        page = context.new_page()

        print("[1/12] Landing Page...")
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_selector('input[type="text"]', timeout=5000)
        page.fill('input[type="text"]', 'admin')
        page.fill('input[type="password"]', 'adminpassword')
        page.click('button[type="submit"]')
        page.wait_for_url(f"{BASE_URL}/command-center", timeout=5000)
        print("  -> Logged in successfully!")

        print("[2/12] Command Center...")
        page.wait_for_selector('text=COMMAND CENTER', timeout=5000)
        time.sleep(2)

        print("[3/12] Live Monitoring...")
        page.goto(f"{BASE_URL}/live-monitoring", wait_until="domcontentloaded")
        page.wait_for_selector('video, .camera-card', timeout=5000)
        time.sleep(2)

        print("[4/12] Vehicle Workspace (GJ18TC0450)...")
        page.goto(f"{BASE_URL}/workspace?plate=GJ18TC0450", wait_until="networkidle")
        page.wait_for_selector('text=GJ18TC0450', timeout=5000)
        time.sleep(2)

        print("[5/12] AI Copilot...")
        page.goto(f"{BASE_URL}/copilot", wait_until="networkidle")
        page.wait_for_selector('text=AI Security Copilot', timeout=5000)
        time.sleep(2)

        print("[6/12] Anomaly Intelligence...")
        page.goto(f"{BASE_URL}/anomalies", wait_until="networkidle")
        page.wait_for_selector('text=Anomalies', timeout=5000)
        time.sleep(2)

        print("[7/12] Investigation Graph...")
        page.goto(f"{BASE_URL}/graph", wait_until="networkidle")
        page.wait_for_selector('canvas, svg, .graph-container', timeout=5000)
        time.sleep(2)

        print("[8/12] Incident Dossier...")
        page.goto(f"{BASE_URL}/incidents/INC-2026-9001", wait_until="networkidle")
        page.wait_for_selector('text=INC-2026-9001', timeout=5000)
        time.sleep(2)

        print("[9/12] Case Dossier...")
        page.goto(f"{BASE_URL}/cases/CASE-2026-9001", wait_until="networkidle")
        page.wait_for_selector('text=CASE-2026-9001', timeout=5000)
        time.sleep(2)

        print("[10/12] Camera Intelligence...")
        page.goto(f"{BASE_URL}/camera-intelligence", wait_until="networkidle")
        page.wait_for_selector('text=Camera Intelligence', timeout=5000)
        time.sleep(2)

        print("[11/12] System Page...")
        page.goto(f"{BASE_URL}/system", wait_until="networkidle")
        page.wait_for_selector('text=System Health', timeout=5000)
        time.sleep(2)

        print("[12/12] Final Screen...")
        page.goto(f"{BASE_URL}/command-center", wait_until="networkidle")
        time.sleep(1)

        context.close()
        browser.close()
        print("\n=== DRY RUN PASSED COMPLETELY WITH 0 ERRORS ===")

if __name__ == "__main__":
    test_recording_flow()

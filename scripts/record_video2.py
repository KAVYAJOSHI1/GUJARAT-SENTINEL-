#!/usr/bin/env python3
"""
SENTINEL — Video 2 Production Recording Script (Playwright Python)

Exact Target Duration: 2 Minutes 45 Seconds (165 Seconds)
Resolution: 1920x1080 (1080p Full HD, 16:9)
Output Directory: ./recordings/
Output File: video2_sentinel_demo.mp4
"""

import os
import sys
import time
import requests
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3000"
API_URL = "http://localhost:8001/api/v1"
RECORDINGS_DIR = os.path.abspath("./recordings")

os.makedirs(RECORDINGS_DIR, exist_ok=True)

def get_auth_token():
    """Fetches a fresh JWT token from backend API."""
    try:
        resp = requests.post(f"{API_URL}/auth/login", json={"username": "admin", "password": "adminpassword"}, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("access_token", "")
    except Exception as e:
        print("API Auth login error:", e)
    return ""

def inject_mouse_pointer(page):
    """Injects a sleek visual mouse cursor dot into the page DOM."""
    try:
        page.evaluate("""() => {
            if (document.getElementById('playwright-mouse-pointer')) return;
            const cursor = document.createElement('div');
            cursor.id = 'playwright-mouse-pointer';
            cursor.style.position = 'fixed';
            cursor.style.top = '0px';
            cursor.style.left = '0px';
            cursor.style.width = '20px';
            cursor.style.height = '20px';
            cursor.style.backgroundColor = 'rgba(59, 130, 246, 0.85)';
            cursor.style.border = '2px solid rgba(255, 255, 255, 0.95)';
            cursor.style.borderRadius = '50%';
            cursor.style.pointerEvents = 'none';
            cursor.style.zIndex = '9999999';
            cursor.style.transition = 'transform 0.12s ease-out, background-color 0.12s ease-out, left 0.05s linear, top 0.05s linear';
            cursor.style.transform = 'translate(-50%, -50%)';
            cursor.style.boxShadow = '0 0 12px rgba(59, 130, 246, 0.6)';
            document.body.appendChild(cursor);
        }""")
    except Exception:
        pass

def move_mouse_smoothly(page, start_x, start_y, end_x, end_y, steps=15, duration_s=0.3):
    """Moves the visual mouse pointer smoothly between coordinates."""
    sleep_per_step = duration_s / max(1, steps)
    for i in range(1, steps + 1):
        x = start_x + (end_x - start_x) * (i / steps)
        y = start_y + (end_y - start_y) * (i / steps)
        page.mouse.move(x, y)
        try:
            page.evaluate(f"""() => {{
                const el = document.getElementById('playwright-mouse-pointer');
                if (el) {{
                    el.style.left = '{x}px';
                    el.style.top = '{y}px';
                }}
            }}""")
        except Exception:
            pass
        time.sleep(sleep_per_step)

def click_element_smoothly(page, selector, current_pos=(960, 540), duration_s=0.4):
    """Locates an element, smoothly moves cursor to it, and clicks with quick timeout fallback."""
    try:
        inject_mouse_pointer(page)
        loc = page.locator(selector).first
        if loc.is_visible(timeout=2000):
            box = loc.bounding_box(timeout=2000)
            if box:
                target_x = box['x'] + box['width'] / 2
                target_y = box['y'] + box['height'] / 2
                move_mouse_smoothly(page, current_pos[0], current_pos[1], target_x, target_y, steps=15, duration_s=duration_s)
                loc.click(timeout=2000)
                return (target_x, target_y)
    except Exception as e:
        print(f"Smooth click fallback for {selector}: {e}")
    try:
        page.click(selector, timeout=2000)
    except Exception:
        pass
    return current_pos

def nav_to(page, path):
    """Navigates directly to URL and injects mouse pointer."""
    page.goto(f"{BASE_URL}{path}", wait_until="domcontentloaded")
    inject_mouse_pointer(page)
    time.sleep(0.5)

def record_video2():
    print("=== STARTING SENTINEL VIDEO 2 PRODUCTION RECORDING ===")
    
    # 1. Obtain real JWT token
    token = get_auth_token()
    print("JWT Token retrieved successfully:", bool(token))
    
    start_time = time.time()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--window-size=1920,1080",
                "--force-color-profile=srgb"
            ]
        )
        
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            color_scheme="dark",
            record_video_dir=RECORDINGS_DIR,
            record_video_size={"width": 1920, "height": 1080}
        )
        
        page = context.new_page()
        cur_pos = (960, 540)

        # ----------------------------------------------------------------------
        # 1. LANDING PAGE (0:00 - 0:07 | 7 Seconds)
        # ----------------------------------------------------------------------
        print("[0:00 - 0:07] 1. Landing Page...")
        page.goto(BASE_URL, wait_until="domcontentloaded")
        inject_mouse_pointer(page)
        time.sleep(0.5)
        
        # Click Sign In button in header
        cur_pos = click_element_smoothly(page, '.ld-nav-cta, button:has-text("Sign in")', cur_pos, duration_s=0.4)
        time.sleep(0.4)
        
        # Fill credentials
        inputs = page.locator('.ld-input')
        if inputs.count() >= 2:
            inputs.nth(0).fill('admin')
            time.sleep(0.3)
            inputs.nth(1).fill('adminpassword')
            time.sleep(0.3)
        
        cur_pos = click_element_smoothly(page, '.ld-submit', cur_pos, duration_s=0.4)
        time.sleep(1.2) # Total: 7s
        
        # Inject token in localStorage for subsequent authenticated navigation
        if token:
            context.add_init_script(f'localStorage.setItem("sentinel_token", "{token}");')
            page.evaluate(f'localStorage.setItem("sentinel_token", "{token}");')

        # ----------------------------------------------------------------------
        # 2. COMMAND CENTER (0:07 - 0:23 | 16 Seconds)
        # ----------------------------------------------------------------------
        print("[0:07 - 0:23] 2. Command Center...")
        nav_to(page, '/command-center')
        time.sleep(2.0)
        
        # Hover metric cards
        move_mouse_smoothly(page, 960, 540, 500, 300, steps=15, duration_s=0.5)
        time.sleep(2.0)
        
        # Hover Watchlist Alert card for GJ18TC0450
        move_mouse_smoothly(page, 500, 300, 400, 550, steps=15, duration_s=0.5)
        time.sleep(2.0)
        
        # Click Investigate CTA
        investigate_btn = page.locator('button:has-text("Investigate"), a:has-text("Investigate"), [href*="/workspace"]').first
        if investigate_btn.is_visible(timeout=2000):
            cur_pos = click_element_smoothly(page, 'button:has-text("Investigate"), a:has-text("Investigate"), [href*="/workspace"]', (400, 550), duration_s=0.5)
            time.sleep(7.0)
        else:
            time.sleep(7.0) # Total: 16s

        # ----------------------------------------------------------------------
        # 3. LIVE MONITORING GRID (0:23 - 0:38 | 15 Seconds)
        # ----------------------------------------------------------------------
        print("[0:23 - 0:38] 3. Live Monitoring Grid...")
        nav_to(page, '/live-monitoring')
        time.sleep(2.0)
        
        # Hover stream 1
        move_mouse_smoothly(page, 960, 540, 450, 400, steps=15, duration_s=0.5)
        time.sleep(5.0)
        
        # Hover stream 2
        move_mouse_smoothly(page, 450, 400, 1200, 400, steps=15, duration_s=0.5)
        time.sleep(6.0) # Total: 15s

        # ----------------------------------------------------------------------
        # 4. VEHICLE WORKSPACE (0:38 - 1:13 | 35 Seconds - MAIN SECTION)
        # ----------------------------------------------------------------------
        print("[0:38 - 1:13] 4. Vehicle Workspace (GJ18TC0450)...")
        nav_to(page, '/workspace?plate=GJ18TC0450')
        time.sleep(3.0)
        
        # 4A. Journey Map (5 Camera Hops)
        move_mouse_smoothly(page, 960, 540, 700, 450, steps=15, duration_s=0.5)
        time.sleep(7.0)
        
        # 4B. Sightings Timeline Tab
        sightings_tab = page.locator('button:has-text("Sightings")').first
        if sightings_tab.is_visible(timeout=2000):
            cur_pos = click_element_smoothly(page, 'button:has-text("Sightings")', (700, 450), duration_s=0.4)
            time.sleep(6.0)
        
        # 4C. ANPR Consensus Tab
        consensus_tab = page.locator('button:has-text("Consensus")').first
        if consensus_tab.is_visible(timeout=2000):
            cur_pos = click_element_smoothly(page, 'button:has-text("Consensus")', cur_pos, duration_s=0.4)
            time.sleep(5.0)
        
        # 4D. Evidence Snapshot Modal
        ev_img = page.locator('img[src*="evidence"], .evidence-thumbnail img, img').first
        if ev_img.is_visible(timeout=2000):
            cur_pos = click_element_smoothly(page, 'img[src*="evidence"], .evidence-thumbnail img, img', cur_pos, duration_s=0.4)
            time.sleep(5.0)
            page.keyboard.press("Escape")
            time.sleep(1.0)
        else:
            time.sleep(6.0) # Total: 35s

        # ----------------------------------------------------------------------
        # 5. AI COPILOT (1:13 - 1:28 | 15 Seconds)
        # ----------------------------------------------------------------------
        print("[1:13 - 1:28] 5. AI Copilot...")
        nav_to(page, '/copilot')
        time.sleep(2.0)
        
        chip = page.locator('button:has-text("GJ18TC0450"), button:has-text("Where was")').first
        if chip.is_visible(timeout=2000):
            cur_pos = click_element_smoothly(page, 'button:has-text("GJ18TC0450"), button:has-text("Where was")', (960, 540), duration_s=0.5)
            time.sleep(5.0)
        else:
            time.sleep(5.0)
        time.sleep(6.5) # Total: 15s

        # ----------------------------------------------------------------------
        # 6. ANOMALY INTELLIGENCE (1:28 - 1:38 | 10 Seconds)
        # ----------------------------------------------------------------------
        print("[1:28 - 1:38] 6. Anomaly Intelligence...")
        nav_to(page, '/anomalies')
        time.sleep(2.0)
        
        move_mouse_smoothly(page, 960, 540, 500, 400, steps=15, duration_s=0.5)
        time.sleep(6.5) # Total: 10s

        # ----------------------------------------------------------------------
        # 7. INVESTIGATION GRAPH (1:38 - 1:56 | 18 Seconds)
        # ----------------------------------------------------------------------
        print("[1:38 - 1:56] 7. Investigation Graph...")
        nav_to(page, '/graph')
        time.sleep(3.0)
        
        cur_pos = click_element_smoothly(page, 'canvas, svg', (960, 540), duration_s=0.5)
        time.sleep(13.5) # Total: 18s

        # ----------------------------------------------------------------------
        # 8. INCIDENT DOSSIER (1:56 - 2:06 | 10 Seconds)
        # ----------------------------------------------------------------------
        print("[1:56 - 2:06] 8. Incident Dossier...")
        nav_to(page, '/incidents/47917f40-b899-49ac-bd31-0c7634e2a091')
        time.sleep(2.0)
        
        page.evaluate("window.scrollBy(0, 300);")
        time.sleep(6.5) # Total: 10s

        # ----------------------------------------------------------------------
        # 9. CASE DOSSIER & REPORT EXPORT (2:06 - 2:21 | 15 Seconds)
        # ----------------------------------------------------------------------
        print("[2:06 - 2:21] 9. Case Dossier & Report Export...")
        nav_to(page, '/cases/a191f4a6-1536-4cf7-8a54-399c1c8017ef')
        time.sleep(3.0)
        
        export_btn = page.locator('button:has-text("Export")').first
        if export_btn.is_visible(timeout=2000):
            cur_pos = click_element_smoothly(page, 'button:has-text("Export")', (960, 540), duration_s=0.5)
            time.sleep(4.0)
        time.sleep(6.5) # Total: 15s

        # ----------------------------------------------------------------------
        # 10. CAMERA INTELLIGENCE (2:21 - 2:31 | 10 Seconds)
        # ----------------------------------------------------------------------
        print("[2:21 - 2:31] 10. Camera Intelligence...")
        nav_to(page, '/camera-intelligence')
        time.sleep(2.0)
        
        move_mouse_smoothly(page, 960, 540, 600, 450, steps=15, duration_s=0.5)
        time.sleep(6.5) # Total: 10s

        # ----------------------------------------------------------------------
        # 11. SYSTEM / AUDIT (2:31 - 2:40 | 9 Seconds)
        # ----------------------------------------------------------------------
        print("[2:31 - 2:40] 11. System Health & Security Audit...")
        nav_to(page, '/system')
        time.sleep(2.0)
        
        page.evaluate("window.scrollBy(0, 350);")
        time.sleep(5.5) # Total: 9s

        # ----------------------------------------------------------------------
        # 12. FINAL SENTINEL SCREEN (2:40 - 2:45 | 5 Seconds)
        # ----------------------------------------------------------------------
        print("[2:40 - 2:45] 12. Final Sentinel Screen...")
        nav_to(page, '/command-center')
        time.sleep(4.5) # Total: 5s hold

        context.close()
        browser.close()
        
        total_real_time = time.time() - start_time
        print(f"\n=== RECORDING EXECUTION COMPLETED IN {total_real_time:.2f} SECONDS ===")

if __name__ == "__main__":
    record_video2()

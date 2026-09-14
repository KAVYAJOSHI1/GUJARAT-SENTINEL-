#!/usr/bin/env python3
"""
SENTINEL — 60-Second Full Implementation Walkthrough Recording Script (Playwright Python)

Exact Target Duration: ~60 Seconds (1 Minute Fast Walkthrough)
Resolution: 1920x1080 (1080p Full HD, 16:9)
Output Directory: ./recordings/
Output File: video_60s_sentinel.mp4
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
        resp = requests.post(f"{API_URL}/auth/login", json={"username": "admin", "password": "local-admin-pass"}, timeout=5)
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
            cursor.style.backgroundColor = 'rgba(59, 130, 246, 0.9)';
            cursor.style.border = '2px solid rgba(255, 255, 255, 0.95)';
            cursor.style.borderRadius = '50%';
            cursor.style.pointerEvents = 'none';
            cursor.style.zIndex = '9999999';
            cursor.style.transition = 'transform 0.1s ease-out, background-color 0.1s ease-out, left 0.04s linear, top 0.04s linear';
            cursor.style.transform = 'translate(-50%, -50%)';
            cursor.style.boxShadow = '0 0 12px rgba(59, 130, 246, 0.8)';
            document.body.appendChild(cursor);
        }""")
    except Exception:
        pass

def move_mouse_smoothly(page, start_x, start_y, end_x, end_y, steps=15, duration_s=0.25):
    """Moves the visual mouse pointer smoothly between coordinates and returns final position."""
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
    return (end_x, end_y)

def click_element_smoothly(page, selector, current_pos=(960, 540), duration_s=0.3):
    """Locates an element, smoothly moves cursor to it, and clicks."""
    try:
        inject_mouse_pointer(page)
        loc = page.locator(selector).first
        if loc.is_visible(timeout=1500):
            box = loc.bounding_box(timeout=1500)
            if box:
                target_x = box['x'] + box['width'] / 2
                target_y = box['y'] + box['height'] / 2
                move_mouse_smoothly(page, current_pos[0], current_pos[1], target_x, target_y, steps=12, duration_s=duration_s)
                loc.click(timeout=1500)
                return (target_x, target_y)
    except Exception as e:
        print(f"Smooth click fallback for {selector}: {e}")
    try:
        page.click(selector, timeout=1500)
    except Exception:
        pass
    return current_pos

def nav_to(page, path):
    """Navigates directly to URL and injects mouse pointer."""
    page.goto(f"{BASE_URL}{path}", wait_until="domcontentloaded")
    inject_mouse_pointer(page)
    time.sleep(0.3)

def record_video_60s_full():
    print("=== STARTING SENTINEL 60-SECOND FULL IMPLEMENTATION WALKTHROUGH RECORDING ===")
    
    token = get_auth_token()
    print("JWT Token retrieved:", bool(token))
    
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
        # 1. LANDING PAGE SMOOTH SCROLL & LOGIN (0:00 - 0:10 | 10s)
        # ----------------------------------------------------------------------
        print("[0:00 - 0:10] 1. Landing Page Smooth Scroll & Login...")
        page.goto(BASE_URL, wait_until="domcontentloaded")
        inject_mouse_pointer(page)
        time.sleep(1.0)
        
        # Smooth scroll down through Problem & Insight section
        page.evaluate("window.scrollBy({top: 600, behavior: 'smooth'});")
        time.sleep(1.2)
        
        # Smooth scroll down to How It Works section
        page.evaluate("window.scrollBy({top: 700, behavior: 'smooth'});")
        time.sleep(1.2)
        
        # Smooth scroll back up to Hero / Header
        page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'});")
        time.sleep(1.0)
        
        # Click Sign In CTA in header
        cur_pos = click_element_smoothly(page, '.ld-nav-cta, button:has-text("Sign in")', cur_pos, duration_s=0.3)
        time.sleep(0.4)
        
        # Fill credentials
        inputs = page.locator('.ld-input')
        if inputs.count() >= 2:
            inputs.nth(0).fill("admin")
            inputs.nth(1).fill("local-admin-pass")
            time.sleep(0.3)
            cur_pos = click_element_smoothly(page, 'button[type="submit"]', cur_pos, duration_s=0.3)
            time.sleep(1.0)
        
        # Ensure auth token in localStorage
        if token:
            page.evaluate(f"localStorage.setItem('sentinel_token', '{token}')")

        # ----------------------------------------------------------------------
        # 2. COMMAND CENTER TELEMETRY (0:10 - 0:15 | 5s)
        # ----------------------------------------------------------------------
        print("[0:10 - 0:15] 2. Command Center Telemetry...")
        nav_to(page, "/dashboard")
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 450, 250, steps=10, duration_s=0.3)
        time.sleep(1.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1200, 300, steps=10, duration_s=0.3)
        time.sleep(1.5)
        page.evaluate("window.scrollBy({top: 300, behavior: 'smooth'});")
        time.sleep(1.4)

        # ----------------------------------------------------------------------
        # 3. LIVE MONITORING WALL (0:15 - 0:20 | 5s)
        # ----------------------------------------------------------------------
        print("[0:15 - 0:20] 3. Live Monitoring Wall...")
        nav_to(page, "/live-feed")
        time.sleep(1.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 600, 400, steps=10, duration_s=0.3)
        time.sleep(1.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1300, 600, steps=10, duration_s=0.3)
        time.sleep(1.4)

        # ----------------------------------------------------------------------
        # 4. VEHICLE WORKSPACE — GJ18TC0450 (0:20 - 0:26 | 6s)
        # ----------------------------------------------------------------------
        print("[0:20 - 0:26] 4. Vehicle Workspace (GJ18TC0450)...")
        nav_to(page, "/vehicles")
        time.sleep(1.2)
        cur_pos = click_element_smoothly(page, 'text="GJ18TC0450"', cur_pos, duration_s=0.3)
        time.sleep(1.5)
        page.evaluate("window.scrollBy({top: 350, behavior: 'smooth'});")
        time.sleep(1.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1100, 450, steps=10, duration_s=0.3)
        time.sleep(1.2)

        # ----------------------------------------------------------------------
        # 5. AI INVESTIGATION COPILOT (0:26 - 0:31 | 5s)
        # ----------------------------------------------------------------------
        print("[0:26 - 0:31] 5. AI Investigation Copilot...")
        nav_to(page, "/ai-copilot")
        time.sleep(1.2)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 800, 500, steps=10, duration_s=0.3)
        time.sleep(1.5)
        page.evaluate("window.scrollBy({top: 300, behavior: 'smooth'});")
        time.sleep(1.8)

        # ----------------------------------------------------------------------
        # 6. AI ANOMALY INTELLIGENCE (0:31 - 0:35 | 4s)
        # ----------------------------------------------------------------------
        print("[0:31 - 0:35] 6. AI Anomaly Intelligence...")
        nav_to(page, "/anomalies")
        time.sleep(1.2)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 700, 350, steps=10, duration_s=0.3)
        time.sleep(1.5)
        page.evaluate("window.scrollBy({top: 250, behavior: 'smooth'});")
        time.sleep(1.0)

        # ----------------------------------------------------------------------
        # 7. INVESTIGATION GRAPH NETWORK (0:35 - 0:40 | 5s)
        # ----------------------------------------------------------------------
        print("[0:35 - 0:40] 7. Investigation Graph Network...")
        nav_to(page, "/graph")
        time.sleep(1.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 960, 500, steps=12, duration_s=0.4)
        time.sleep(1.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1200, 400, steps=10, duration_s=0.3)
        time.sleep(1.3)

        # ----------------------------------------------------------------------
        # 8. INCIDENT CENTER & CASE DOSSIER (0:40 - 0:45 | 5s)
        # ----------------------------------------------------------------------
        print("[0:40 - 0:45] 8. Incident Center & Case Dossier...")
        nav_to(page, "/incidents")
        time.sleep(1.2)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 600, 350, steps=10, duration_s=0.3)
        time.sleep(1.0)
        nav_to(page, "/cases")
        time.sleep(1.2)
        page.evaluate("window.scrollBy({top: 300, behavior: 'smooth'});")
        time.sleep(1.3)

        # ----------------------------------------------------------------------
        # 9. CAMERA RELIABILITY INTELLIGENCE (0:45 - 0:50 | 5s)
        # ----------------------------------------------------------------------
        print("[0:45 - 0:50] 9. Camera Reliability Intelligence...")
        nav_to(page, "/cameras")
        time.sleep(1.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 500, 400, steps=10, duration_s=0.3)
        time.sleep(1.5)
        page.evaluate("window.scrollBy({top: 300, behavior: 'smooth'});")
        time.sleep(1.7)

        # ----------------------------------------------------------------------
        # 10. OPERATIONS, SEARCH & GIS MAP (0:50 - 0:55 | 5s)
        # ----------------------------------------------------------------------
        print("[0:50 - 0:55] 10. Operations, Search & GIS Map...")
        nav_to(page, "/map")
        time.sleep(1.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 960, 540, steps=12, duration_s=0.4)
        time.sleep(1.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1150, 420, steps=10, duration_s=0.3)
        time.sleep(1.3)

        # ----------------------------------------------------------------------
        # 11. SYSTEM AUDIT & FINAL DASHBOARD (0:55 - 1:00 | 5s)
        # ----------------------------------------------------------------------
        print("[0:55 - 1:00] 11. System Audit & Closing Dashboard...")
        nav_to(page, "/system")
        time.sleep(1.2)
        nav_to(page, "/dashboard")
        time.sleep(1.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 960, 500, steps=10, duration_s=0.3)
        time.sleep(1.0)
        
        context.close()
        browser.close()
        
    elapsed = time.time() - start_time
    print(f"\n=== 60-SECOND RECORDING EXECUTION COMPLETED IN {elapsed:.2f} SECONDS ===")

if __name__ == "__main__":
    record_video_60s_full()

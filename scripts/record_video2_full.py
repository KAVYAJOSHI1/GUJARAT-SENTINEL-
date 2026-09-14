#!/usr/bin/env python3
"""
SENTINEL — Video 2 Production Recording Script (Playwright Python)

Exact Target Duration: 3 Minutes 30 Seconds (210 Seconds)
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
            cursor.style.width = '22px';
            cursor.style.height = '22px';
            cursor.style.backgroundColor = 'rgba(59, 130, 246, 0.85)';
            cursor.style.border = '2px solid rgba(255, 255, 255, 0.95)';
            cursor.style.borderRadius = '50%';
            cursor.style.pointerEvents = 'none';
            cursor.style.zIndex = '9999999';
            cursor.style.transition = 'transform 0.12s ease-out, background-color 0.12s ease-out, left 0.05s linear, top 0.05s linear';
            cursor.style.transform = 'translate(-50%, -50%)';
            cursor.style.boxShadow = '0 0 14px rgba(59, 130, 246, 0.7)';
            document.body.appendChild(cursor);
        }""")
    except Exception:
        pass

def move_mouse_smoothly(page, start_x, start_y, end_x, end_y, steps=20, duration_s=0.4):
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

def click_element_smoothly(page, selector, current_pos=(960, 540), duration_s=0.5):
    """Locates an element, smoothly moves cursor to it, and clicks with quick timeout fallback."""
    try:
        inject_mouse_pointer(page)
        loc = page.locator(selector).first
        if loc.is_visible(timeout=2000):
            box = loc.bounding_box(timeout=2000)
            if box:
                target_x = box['x'] + box['width'] / 2
                target_y = box['y'] + box['height'] / 2
                move_mouse_smoothly(page, current_pos[0], current_pos[1], target_x, target_y, steps=20, duration_s=duration_s)
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

def record_video2_full():
    print("=== STARTING SENTINEL VIDEO 2 FULL PRODUCTION RECORDING ===")
    
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
        # 1. LANDING PAGE & AUTHENTICATION (0:00 - 0:12 | 12 Seconds)
        # ----------------------------------------------------------------------
        print("[0:00 - 0:12] 1. Landing Page & Authentication...")
        page.goto(BASE_URL, wait_until="domcontentloaded")
        inject_mouse_pointer(page)
        time.sleep(1.5) # Showcase hero aperture & headline
        
        # Scroll down noise grid
        page.evaluate("window.scrollBy({top: 400, behavior: 'smooth'});")
        time.sleep(1.5)
        
        # Click Sign In button in header
        cur_pos = click_element_smoothly(page, '.ld-nav-cta, button:has-text("Sign in")', cur_pos, duration_s=0.5)
        time.sleep(0.6)
        
        # Fill credentials
        inputs = page.locator('.ld-input')
        if inputs.count() >= 2:
            inputs.nth(0).fill('admin')
            time.sleep(0.4)
            inputs.nth(1).fill('adminpassword')
            time.sleep(0.4)
        
        cur_pos = click_element_smoothly(page, '.ld-submit', cur_pos, duration_s=0.5)
        time.sleep(2.0) # Total: 12s
        
        # Inject token in localStorage for subsequent authenticated navigation
        if token:
            context.add_init_script(f'localStorage.setItem("sentinel_token", "{token}");')
            page.evaluate(f'localStorage.setItem("sentinel_token", "{token}");')

        # ----------------------------------------------------------------------
        # 2. COMMAND CENTER TELEMETRY (0:12 - 0:28 | 16 Seconds)
        # ----------------------------------------------------------------------
        print("[0:12 - 0:28] 2. Command Center Telemetry...")
        nav_to(page, '/command-center')
        time.sleep(2.5)
        
        # Hover metric cards
        move_mouse_smoothly(page, 960, 540, 500, 300, steps=20, duration_s=0.6)
        time.sleep(2.5)
        
        # Hover Watchlist Alert card for GJ18TC0450
        move_mouse_smoothly(page, 500, 300, 400, 550, steps=20, duration_s=0.6)
        time.sleep(2.5)
        
        # Click Investigate CTA
        investigate_btn = page.locator('button:has-text("Investigate"), a:has-text("Investigate"), [href*="/workspace"]').first
        if investigate_btn.is_visible(timeout=2000):
            cur_pos = click_element_smoothly(page, 'button:has-text("Investigate"), a:has-text("Investigate"), [href*="/workspace"]', (400, 550), duration_s=0.5)
            time.sleep(7.9)
        else:
            time.sleep(7.9) # Total: 16s

        # ----------------------------------------------------------------------
        # 3. LIVE MONITORING WALL (0:28 - 0:45 | 17 Seconds)
        # ----------------------------------------------------------------------
        print("[0:28 - 0:45] 3. Live Monitoring Wall...")
        nav_to(page, '/live-monitoring')
        time.sleep(2.5)
        
        # Hover stream 1 (CAM-01)
        move_mouse_smoothly(page, 960, 540, 450, 400, steps=20, duration_s=0.6)
        time.sleep(6.0)
        
        # Hover stream 2 (CAM-02)
        move_mouse_smoothly(page, 450, 400, 1200, 400, steps=20, duration_s=0.6)
        time.sleep(7.9) # Total: 17s

        # ----------------------------------------------------------------------
        # 4. VEHICLE WORKSPACE - TARGET GJ18TC0450 (0:45 - 1:25 | 40 Seconds)
        # ----------------------------------------------------------------------
        print("[0:45 - 1:25] 4. Vehicle Workspace (GJ18TC0450)...")
        nav_to(page, '/workspace?plate=GJ18TC0450')
        time.sleep(3.5) # Profile header highlight
        
        # 4A. 5-Camera GIS Journey Map
        move_mouse_smoothly(page, 960, 540, 700, 450, steps=20, duration_s=0.6)
        time.sleep(8.0) # 5-camera route polyline
        
        # 4B. Sightings Timeline Tab
        sightings_tab = page.locator('button:has-text("Sightings")').first
        if sightings_tab.is_visible(timeout=2000):
            cur_pos = click_element_smoothly(page, 'button:has-text("Sightings")', (700, 450), duration_s=0.5)
            time.sleep(7.0)
        
        # 4C. ANPR Consensus Engine Tab
        consensus_tab = page.locator('button:has-text("Consensus")').first
        if consensus_tab.is_visible(timeout=2000):
            cur_pos = click_element_smoothly(page, 'button:has-text("Consensus")', cur_pos, duration_s=0.5)
            time.sleep(6.5)
        
        # 4D. Evidence Snapshot Modal
        ev_img = page.locator('img[src*="evidence"], .evidence-thumbnail img, img').first
        if ev_img.is_visible(timeout=2000):
            cur_pos = click_element_smoothly(page, 'img[src*="evidence"], .evidence-thumbnail img, img', cur_pos, duration_s=0.5)
            time.sleep(6.0) # Inspect high-res crop & bounding box
            page.keyboard.press("Escape")
            time.sleep(1.5)
        else:
            time.sleep(7.5) # Total: 40s

        # ----------------------------------------------------------------------
        # 5. AI INVESTIGATION COPILOT (1:25 - 1:45 | 20 Seconds)
        # ----------------------------------------------------------------------
        print("[1:25 - 1:45] 5. AI Investigation Copilot...")
        nav_to(page, '/copilot')
        time.sleep(2.5)
        
        chip = page.locator('button:has-text("GJ18TC0450"), button:has-text("Where was")').first
        if chip.is_visible(timeout=2000):
            cur_pos = click_element_smoothly(page, 'button:has-text("GJ18TC0450"), button:has-text("Where was")', (960, 540), duration_s=0.6)
            time.sleep(7.5)
        else:
            time.sleep(7.5)
        time.sleep(10.0) # Total: 20s

        # ----------------------------------------------------------------------
        # 6. AI ANOMALY INTELLIGENCE (1:45 - 1:58 | 13 Seconds)
        # ----------------------------------------------------------------------
        print("[1:45 - 1:58] 6. AI Anomaly Intelligence...")
        nav_to(page, '/anomalies')
        time.sleep(2.5)
        
        move_mouse_smoothly(page, 960, 540, 500, 400, steps=20, duration_s=0.6)
        time.sleep(10.5) # Total: 13s

        # ----------------------------------------------------------------------
        # 7. INVESTIGATION GRAPH NETWORK (1:58 - 2:15 | 17 Seconds)
        # ----------------------------------------------------------------------
        print("[1:58 - 2:15] 7. Investigation Graph Network...")
        nav_to(page, '/graph')
        time.sleep(3.5) # Allow D3/Vis physics simulation to settle
        
        cur_pos = click_element_smoothly(page, 'canvas, svg', (960, 540), duration_s=0.6)
        time.sleep(13.5) # Total: 17s

        # ----------------------------------------------------------------------
        # 8. INCIDENT CENTER & DOSSIER (2:15 - 2:30 | 15 Seconds)
        # ----------------------------------------------------------------------
        print("[2:15 - 2:30] 8. Incident Center & Incident Dossier...")
        nav_to(page, '/incidents/47917f40-b899-49ac-bd31-0c7634e2a091')
        time.sleep(3.0)
        
        page.evaluate("window.scrollBy({top: 350, behavior: 'smooth'});")
        time.sleep(12.0) # Total: 15s

        # ----------------------------------------------------------------------
        # 9. CASE DOSSIER & REPORT EXPORT (2:30 - 2:48 | 18 Seconds)
        # ----------------------------------------------------------------------
        print("[2:30 - 2:48] 9. Case Dossier & Report Export...")
        nav_to(page, '/cases/a191f4a6-1536-4cf7-8a54-399c1c8017ef')
        time.sleep(3.5)
        
        export_btn = page.locator('button:has-text("Export")').first
        if export_btn.is_visible(timeout=2000):
            cur_pos = click_element_smoothly(page, 'button:has-text("Export")', (960, 540), duration_s=0.6)
            time.sleep(5.0)
        time.sleep(9.5) # Total: 18s

        # ----------------------------------------------------------------------
        # 10. CAMERA RELIABILITY INTELLIGENCE (2:48 - 3:00 | 12 Seconds)
        # ----------------------------------------------------------------------
        print("[2:48 - 3:00] 10. Camera Reliability Intelligence...")
        nav_to(page, '/camera-intelligence')
        time.sleep(2.5)
        
        move_mouse_smoothly(page, 960, 540, 600, 450, steps=20, duration_s=0.6)
        time.sleep(9.5) # Total: 12s

        # ----------------------------------------------------------------------
        # 11. OPERATIONS, SEARCH & GIS MAP (3:00 - 3:12 | 12 Seconds)
        # ----------------------------------------------------------------------
        print("[3:00 - 3:12] 11. Operations, Search & GIS Map...")
        nav_to(page, '/search')
        time.sleep(2.5)
        
        nav_to(page, '/map')
        time.sleep(4.0)
        move_mouse_smoothly(page, 960, 540, 750, 500, steps=20, duration_s=0.6)
        time.sleep(5.5) # Total: 12s

        # ----------------------------------------------------------------------
        # 12. SYSTEM & SECURITY AUDIT (3:12 - 3:22 | 10 Seconds)
        # ----------------------------------------------------------------------
        print("[3:12 - 3:22] 12. System Infrastructure & Security Audit...")
        nav_to(page, '/system')
        time.sleep(2.5)
        
        page.evaluate("window.scrollBy({top: 350, behavior: 'smooth'});")
        time.sleep(7.5) # Total: 10s

        # ----------------------------------------------------------------------
        # 13. FINAL COMMAND CENTER CLOSING HOLD (3:22 - 3:30 | 8 Seconds)
        # ----------------------------------------------------------------------
        print("[3:22 - 3:30] 13. Final Command Center Closing Hold...")
        nav_to(page, '/command-center')
        time.sleep(7.5) # Total: 8s hold

        context.close()
        browser.close()
        
        total_real_time = time.time() - start_time
        print(f"\n=== RECORDING EXECUTION COMPLETED IN {total_real_time:.2f} SECONDS ===")

if __name__ == "__main__":
    record_video2_full()

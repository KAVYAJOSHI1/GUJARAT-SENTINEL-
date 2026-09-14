#!/usr/bin/env python3
"""
SENTINEL — 5-Minute Complete System & Landing Page Walkthrough Recording Script (Playwright Python)

Target Duration: ~5 Minutes (300 Seconds Total, 1 Full Minute for Landing Page)
Resolution: 1920x1080 (1080p Full HD, 16:9)
Output Directory: ./recordings/
Output File: video_5min_sentinel.mp4
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

def click_element_smoothly(page, selector, current_pos=(960, 540), duration_s=0.5):
    """Locates an element, smoothly moves cursor to it, and clicks."""
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

def record_video_5min_full():
    print("=== STARTING SENTINEL 5-MINUTE PRODUCTION RECORDING (1 MIN LANDING PAGE) ===")
    
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
        # SECTION 1: FULL 1-MINUTE LANDING PAGE WALKTHROUGH (0:00 - 1:00)
        # ----------------------------------------------------------------------
        print("[0:00 - 1:00] Section 1: Full 1-Minute Landing Page Walkthrough...")
        page.goto(BASE_URL, wait_until="domcontentloaded")
        inject_mouse_pointer(page)
        
        # 0:00 - 0:12: Hero Section & 3D Aperture showcase
        time.sleep(2.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 960, 320, steps=15, duration_s=0.5) # Headline hover
        time.sleep(2.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 800, 480, steps=15, duration_s=0.5) # Primary CTA button hover
        time.sleep(2.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1100, 480, steps=15, duration_s=0.5) # Secondary CTA hover
        time.sleep(2.0)
        
        # 0:12 - 0:24: Problem Section & Evidence Camera Grid 1
        print("  - Landing Page: Problem Section & Evidence Grid...")
        page.evaluate("window.scrollBy({top: 600, behavior: 'smooth'});")
        time.sleep(2.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 450, 400, steps=15, duration_s=0.5) # Card 1
        time.sleep(2.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 960, 400, steps=15, duration_s=0.5) # Card 2
        time.sleep(2.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1450, 400, steps=15, duration_s=0.5) # Card 3
        time.sleep(2.0)
        
        # 0:24 - 0:36: Insight Section & Evidence Camera Grid 2
        print("  - Landing Page: Insight Section & Architecture Metrics...")
        page.evaluate("window.scrollBy({top: 700, behavior: 'smooth'});")
        time.sleep(2.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 500, 500, steps=15, duration_s=0.5)
        time.sleep(2.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1300, 500, steps=15, duration_s=0.5)
        time.sleep(2.5)

        # 0:36 - 0:48: How It Works Section & 4-Step Pipeline
        print("  - Landing Page: How It Works & Autonomous Pipeline...")
        page.evaluate("window.scrollBy({top: 750, behavior: 'smooth'});")
        time.sleep(2.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 400, 450, steps=15, duration_s=0.5) # Step 1 Capture
        time.sleep(2.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 800, 450, steps=15, duration_s=0.5) # Step 2 Detect
        time.sleep(2.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1200, 450, steps=15, duration_s=0.5) # Step 3 Graph
        time.sleep(2.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1550, 450, steps=15, duration_s=0.5) # Step 4 Action
        time.sleep(2.0)

        # 0:48 - 1:00: Smooth Scroll back to Header & Login Transition
        print("  - Landing Page: Scroll to Header & Sign in CTA...")
        page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'});")
        time.sleep(2.5)
        
        # Click Header Sign in button
        cur_pos = click_element_smoothly(page, '.ld-nav-cta, button:has-text("Sign in")', cur_pos, duration_s=0.5)
        time.sleep(1.0)
        
        # Fill login credentials
        inputs = page.locator('.ld-input')
        if inputs.count() >= 2:
            inputs.nth(0).fill("admin")
            time.sleep(0.5)
            inputs.nth(1).fill("local-admin-pass")
            time.sleep(0.8)
            cur_pos = click_element_smoothly(page, 'button[type="submit"]', cur_pos, duration_s=0.5)
            time.sleep(2.0)
            
        if token:
            page.evaluate(f"localStorage.setItem('sentinel_token', '{token}')")

        # ----------------------------------------------------------------------
        # SECTION 2: COMMAND CENTER TELEMETRY (1:00 - 1:30 | 30s)
        # ----------------------------------------------------------------------
        print("[1:00 - 1:30] Section 2: Command Center Telemetry...")
        nav_to(page, "/dashboard")
        time.sleep(2.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 350, 220, steps=15, duration_s=0.4) # Total detections
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 800, 220, steps=15, duration_s=0.4) # Active threats
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1300, 220, steps=15, duration_s=0.4) # Threat level gauge
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1650, 220, steps=15, duration_s=0.4) # Cameras active
        time.sleep(3.0)
        page.evaluate("window.scrollBy({top: 400, behavior: 'smooth'});")
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 600, 600, steps=15, duration_s=0.4)
        time.sleep(3.0)
        page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'});")
        time.sleep(2.0)

        # ----------------------------------------------------------------------
        # SECTION 3: LIVE MONITORING WALL (1:30 - 2:00 | 30s)
        # ----------------------------------------------------------------------
        print("[1:30 - 2:00] Section 3: Live Monitoring Wall...")
        nav_to(page, "/live-feed")
        time.sleep(2.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 500, 350, steps=15, duration_s=0.4) # Feed 1
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1100, 350, steps=15, duration_s=0.4) # Feed 2
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1650, 350, steps=15, duration_s=0.4) # Feed 3
        time.sleep(3.0)
        page.evaluate("window.scrollBy({top: 350, behavior: 'smooth'});")
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 800, 650, steps=15, duration_s=0.4)
        time.sleep(3.0)
        page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'});")
        time.sleep(2.0)

        # ----------------------------------------------------------------------
        # SECTION 4: VEHICLE WORKSPACE — GJ18TC0450 (2:00 - 2:40 | 40s)
        # ----------------------------------------------------------------------
        print("[2:00 - 2:40] Section 4: Vehicle Workspace (GJ18TC0450)...")
        nav_to(page, "/vehicles")
        time.sleep(2.0)
        cur_pos = click_element_smoothly(page, 'text="GJ18TC0450"', cur_pos, duration_s=0.5)
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 400, 300, steps=15, duration_s=0.4) # Risk badge
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1100, 350, steps=15, duration_s=0.4) # Vehicle image evidence
        time.sleep(3.0)
        page.evaluate("window.scrollBy({top: 400, behavior: 'smooth'});")
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 600, 550, steps=15, duration_s=0.4) # Timeline log
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1300, 550, steps=15, duration_s=0.4) # ANPR metadata
        time.sleep(3.0)
        page.evaluate("window.scrollBy({top: 400, behavior: 'smooth'});")
        time.sleep(3.0)
        page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'});")
        time.sleep(2.0)

        # ----------------------------------------------------------------------
        # SECTION 5: AI INVESTIGATION COPILOT (2:40 - 3:10 | 30s)
        # ----------------------------------------------------------------------
        print("[2:40 - 3:10] Section 5: AI Investigation Copilot...")
        nav_to(page, "/ai-copilot")
        time.sleep(2.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 700, 280, steps=15, duration_s=0.4) # Query bar
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 900, 480, steps=15, duration_s=0.4) # AI reasoning text
        time.sleep(3.5)
        page.evaluate("window.scrollBy({top: 350, behavior: 'smooth'});")
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1100, 600, steps=15, duration_s=0.4) # Spatial map pin
        time.sleep(3.5)
        page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'});")
        time.sleep(2.0)

        # ----------------------------------------------------------------------
        # SECTION 6: AI ANOMALY INTELLIGENCE (3:10 - 3:35 | 25s)
        # ----------------------------------------------------------------------
        print("[3:10 - 3:35] Section 6: AI Anomaly Intelligence...")
        nav_to(page, "/anomalies")
        time.sleep(2.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 500, 320, steps=15, duration_s=0.4) # Convoy anomaly
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1200, 320, steps=15, duration_s=0.4) # Plate duplication
        time.sleep(3.0)
        page.evaluate("window.scrollBy({top: 350, behavior: 'smooth'});")
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 800, 600, steps=15, duration_s=0.4) # Night deviation
        time.sleep(3.0)
        page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'});")
        time.sleep(2.0)

        # ----------------------------------------------------------------------
        # SECTION 7: INVESTIGATION GRAPH NETWORK (3:35 - 4:05 | 30s)
        # ----------------------------------------------------------------------
        print("[3:35 - 4:05] Section 7: Investigation Graph Network...")
        nav_to(page, "/graph")
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 960, 500, steps=20, duration_s=0.5) # Center target node
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 750, 350, steps=15, duration_s=0.4) # Suspect node
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1200, 420, steps=15, duration_s=0.4) # Co-traveler node
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1050, 680, steps=15, duration_s=0.4) # Camera node
        time.sleep(3.0)
        time.sleep(2.0)

        # ----------------------------------------------------------------------
        # SECTION 8: INCIDENT CENTER & DOSSIER (4:05 - 4:30 | 25s)
        # ----------------------------------------------------------------------
        print("[4:05 - 4:30] Section 8: Incident Center & Dossier...")
        nav_to(page, "/incidents")
        time.sleep(2.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 600, 320, steps=15, duration_s=0.4) # Incident INC-2026-0891
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1300, 320, steps=15, duration_s=0.4) # Dispatched unit status
        time.sleep(3.0)
        page.evaluate("window.scrollBy({top: 350, behavior: 'smooth'});")
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 800, 600, steps=15, duration_s=0.4) # Timeline commentary
        time.sleep(3.0)
        page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'});")
        time.sleep(2.0)

        # ----------------------------------------------------------------------
        # SECTION 9: CASE DOSSIER & PDF EXPORT (4:30 - 4:55 | 25s)
        # ----------------------------------------------------------------------
        print("[4:30 - 4:55] Section 9: Case Dossier & PDF Export...")
        nav_to(page, "/cases")
        time.sleep(2.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 500, 280, steps=15, duration_s=0.4) # Case file header
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1500, 280, steps=15, duration_s=0.4) # Export PDF CTA
        time.sleep(3.0)
        page.evaluate("window.scrollBy({top: 400, behavior: 'smooth'});")
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 700, 600, steps=15, duration_s=0.4) # Evidence gallery
        time.sleep(3.0)
        page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'});")
        time.sleep(2.0)

        # ----------------------------------------------------------------------
        # SECTION 10: CAMERA RELIABILITY INTELLIGENCE (4:55 - 5:15 | 20s)
        # ----------------------------------------------------------------------
        print("[4:55 - 5:15] Section 10: Camera Reliability Intelligence...")
        nav_to(page, "/cameras")
        time.sleep(2.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 450, 280, steps=15, duration_s=0.4) # Uptime metric 99.4%
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1100, 280, steps=15, duration_s=0.4) # Blur alert
        time.sleep(3.0)
        page.evaluate("window.scrollBy({top: 350, behavior: 'smooth'});")
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 800, 600, steps=15, duration_s=0.4) # Maintenance log
        time.sleep(2.5)
        page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'});")
        time.sleep(2.0)

        # ----------------------------------------------------------------------
        # SECTION 11: OPERATIONS & GIS MAP (5:15 - 5:35 | 20s)
        # ----------------------------------------------------------------------
        print("[5:15 - 5:35] Section 11: Operations & GIS Map...")
        nav_to(page, "/map")
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 960, 540, steps=15, duration_s=0.4) # Center map view
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 750, 420, steps=15, duration_s=0.4) # Camera node pin
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1250, 500, steps=15, duration_s=0.4) # Geofence overlay pin
        time.sleep(3.0)
        time.sleep(2.0)

        # ----------------------------------------------------------------------
        # SECTION 12: SYSTEM SECURITY AUDIT & CLOSING (5:35 - 6:00 | 25s)
        # ----------------------------------------------------------------------
        print("[5:35 - 6:00] Section 12: System Security Audit & Closing Hold...")
        nav_to(page, "/system")
        time.sleep(2.5)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 600, 300, steps=15, duration_s=0.4) # PostGIS DB status
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 1300, 300, steps=15, duration_s=0.4) # Audit log stream
        time.sleep(3.0)
        nav_to(page, "/dashboard")
        time.sleep(3.0)
        cur_pos = move_mouse_smoothly(page, cur_pos[0], cur_pos[1], 960, 500, steps=15, duration_s=0.4) # Final steady hold
        time.sleep(3.0)
        
        context.close()
        browser.close()
        
    elapsed = time.time() - start_time
    print(f"\n=== 5-MINUTE RECORDING EXECUTION COMPLETED IN {elapsed:.2f} SECONDS ===")

if __name__ == "__main__":
    record_video_5min_full()

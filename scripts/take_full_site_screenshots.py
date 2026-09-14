#!/usr/bin/env python3
"""
SENTINEL — Full Application High-Resolution Screenshot Suite (Playwright Python)

Captures exhaustive, pixel-perfect 1920x1080 screenshots of every page, tab, section, and modal
from the unauthenticated Landing Page to the System Audit log.

Output Directory: ./screenshots/ & ./screen_shot/
"""

import os
import sys
import time
import requests
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:3000"
API_URL = "http://localhost:8001/api/v1"
OUTPUT_DIR = os.path.abspath("./screenshots")
ALT_DIR = os.path.abspath("./screen_shot")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ALT_DIR, exist_ok=True)

def get_auth_token():
    """Fetches a fresh JWT token from backend API."""
    try:
        resp = requests.post(f"{API_URL}/auth/login", json={"username": "admin", "password": "local-admin-pass"}, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("access_token", "")
    except Exception as e:
        print("API Auth login error:", e)
    return ""

def save_screenshot(page, filename, description=""):
    """Saves high-res screenshot to both ./screenshots/ and ./screen_shot/."""
    path1 = os.path.join(OUTPUT_DIR, filename)
    path2 = os.path.join(ALT_DIR, filename)
    page.screenshot(path=path1, full_page=False)
    page.screenshot(path=path2, full_page=False)
    print(f" Saved [{filename}]: {description}")

def nav_to(page, path, wait_s=1.2):
    """Navigates to URL and waits for render."""
    page.goto(f"{BASE_URL}{path}", wait_until="domcontentloaded")
    time.sleep(wait_s)

def run_screenshot_suite():
    print("=== STARTING SENTINEL EXHAUSTIVE SCREENSHOT CAPTURE ===")
    token = get_auth_token()
    print("JWT Token acquired:", bool(token))

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
            color_scheme="dark"
        )

        page = context.new_page()

        # ----------------------------------------------------------------------
        # 1. LANDING PAGE EXHAUSTIVE SCREENSHOTS (UNAUTHENTICATED)
        # ----------------------------------------------------------------------
        print("\n--- 1. Landing Page Section ---")
        page.goto(BASE_URL, wait_until="domcontentloaded")
        time.sleep(1.5)
        save_screenshot(page, "01_landing_01_hero.png", "Landing Page - Hero & 3D Aperture")

        page.evaluate("window.scrollTo({top: 600, behavior: 'instant'});")
        time.sleep(1.0)
        save_screenshot(page, "01_landing_02_problem.png", "Landing Page - Problem Section & Camera Grid 1")

        page.evaluate("window.scrollTo({top: 1300, behavior: 'instant'});")
        time.sleep(1.0)
        save_screenshot(page, "01_landing_03_insight.png", "Landing Page - Insight Section & Camera Grid 2")

        page.evaluate("window.scrollTo({top: 2050, behavior: 'instant'});")
        time.sleep(1.0)
        save_screenshot(page, "01_landing_04_how_it_works.png", "Landing Page - How It Works 4-Step Pipeline")

        page.evaluate("window.scrollTo({top: 0, behavior: 'instant'});")
        time.sleep(0.5)
        
        # Click Sign In CTA in header
        try:
            cta = page.locator('.ld-nav-cta, button:has-text("Sign in")').first
            if cta.is_visible():
                cta.click()
                time.sleep(0.8)
                save_screenshot(page, "01_landing_05_auth_modal.png", "Landing Page - Login Modal Form")
                
                inputs = page.locator('.ld-input')
                if inputs.count() >= 2:
                    inputs.nth(0).fill("admin")
                    inputs.nth(1).fill("local-admin-pass")
                    time.sleep(0.4)
                    page.locator('button[type="submit"]').click()
                    time.sleep(1.5)
        except Exception as e:
            print("Sign in click exception:", e)

        # Inject auth token into localStorage
        if token:
            page.evaluate(f"localStorage.setItem('sentinel_token', '{token}')")

        # ----------------------------------------------------------------------
        # 2. COMMAND CENTER TELEMETRY DASHBOARD (/dashboard)
        # ----------------------------------------------------------------------
        print("\n--- 2. Command Center Telemetry Dashboard ---")
        nav_to(page, "/dashboard")
        save_screenshot(page, "02_dashboard_01_telemetry_top.png", "Dashboard - Top Metrics & Active Threats")

        page.evaluate("window.scrollTo({top: 400, behavior: 'instant'});")
        time.sleep(0.8)
        save_screenshot(page, "02_dashboard_02_hot_zones_stream.png", "Dashboard - Hot Zone Alerts & Live Stream Preview")

        page.evaluate("window.scrollTo({top: 800, behavior: 'instant'});")
        time.sleep(0.8)
        save_screenshot(page, "02_dashboard_03_recent_detections.png", "Dashboard - Recent Detections Stream")

        page.evaluate("window.scrollTo({top: 0, behavior: 'instant'});")

        # ----------------------------------------------------------------------
        # 3. LIVE MONITORING WALL (/live-feed)
        # ----------------------------------------------------------------------
        print("\n--- 3. Live Monitoring Wall ---")
        nav_to(page, "/live-feed")
        save_screenshot(page, "03_live_feed_01_grid_top.png", "Live Feed - Multi-Camera Feed Grid (Top)")

        page.evaluate("window.scrollTo({top: 450, behavior: 'instant'});")
        time.sleep(0.8)
        save_screenshot(page, "03_live_feed_02_grid_bottom.png", "Live Feed - Multi-Camera Feed Grid (Bottom)")
        page.evaluate("window.scrollTo({top: 0, behavior: 'instant'});")

        # ----------------------------------------------------------------------
        # 4. VEHICLE WORKSPACE — GJ18TC0450 (/vehicles)
        # ----------------------------------------------------------------------
        print("\n--- 4. Vehicle Workspace ---")
        nav_to(page, "/vehicles")
        save_screenshot(page, "04_vehicles_01_search_list.png", "Vehicles - Search & List View")

        try:
            target = page.locator('text="GJ18TC0450"').first
            if target.is_visible():
                target.click()
                time.sleep(1.2)
        except Exception:
            pass

        save_screenshot(page, "04_vehicles_02_target_GJ18TC0450_overview.png", "Vehicles - Target GJ18TC0450 Overview & Risk Score")

        page.evaluate("window.scrollTo({top: 400, behavior: 'instant'});")
        time.sleep(0.8)
        save_screenshot(page, "04_vehicles_03_target_timeline.png", "Vehicles - Target GJ18TC0450 Camera Sequence Timeline")

        page.evaluate("window.scrollTo({top: 800, behavior: 'instant'});")
        time.sleep(0.8)
        save_screenshot(page, "04_vehicles_04_target_anpr_metadata.png", "Vehicles - ANPR Read History & Confidence Metadata")
        page.evaluate("window.scrollTo({top: 0, behavior: 'instant'});")

        # ----------------------------------------------------------------------
        # 5. AI INVESTIGATION COPILOT (/ai-copilot)
        # ----------------------------------------------------------------------
        print("\n--- 5. AI Investigation Copilot ---")
        nav_to(page, "/ai-copilot")
        save_screenshot(page, "05_ai_copilot_01_query.png", "AI Copilot - Search Query & Input Interface")

        page.evaluate("window.scrollTo({top: 350, behavior: 'instant'});")
        time.sleep(0.8)
        save_screenshot(page, "05_ai_copilot_02_reasoning_response.png", "AI Copilot - Spatial Reasoning & Copilot Response")

        page.evaluate("window.scrollTo({top: 700, behavior: 'instant'});")
        time.sleep(0.8)
        save_screenshot(page, "05_ai_copilot_03_map_overlay.png", "AI Copilot - Map Pin Overlay")
        page.evaluate("window.scrollTo({top: 0, behavior: 'instant'});")

        # ----------------------------------------------------------------------
        # 6. AI ANOMALY INTELLIGENCE (/anomalies)
        # ----------------------------------------------------------------------
        print("\n--- 6. AI Anomaly Intelligence ---")
        nav_to(page, "/anomalies")
        save_screenshot(page, "06_anomalies_01_summary.png", "AI Anomalies - Dashboard & Distribution")

        page.evaluate("window.scrollTo({top: 350, behavior: 'instant'});")
        time.sleep(0.8)
        save_screenshot(page, "06_anomalies_02_convoy_detection.png", "AI Anomalies - Convoy Detection & Plate Duplication")

        page.evaluate("window.scrollTo({top: 700, behavior: 'instant'});")
        time.sleep(0.8)
        save_screenshot(page, "06_anomalies_03_night_deviation.png", "AI Anomalies - Night Pattern Deviation")
        page.evaluate("window.scrollTo({top: 0, behavior: 'instant'});")

        # ----------------------------------------------------------------------
        # 7. INVESTIGATION GRAPH NETWORK (/graph)
        # ----------------------------------------------------------------------
        print("\n--- 7. Investigation Graph Network ---")
        nav_to(page, "/graph")
        save_screenshot(page, "07_graph_01_full_network.png", "Graph - Force-Directed Graph Centered on Target Vehicle")

        # ----------------------------------------------------------------------
        # 8. INCIDENT CENTER & DOSSIER (/incidents)
        # ----------------------------------------------------------------------
        print("\n--- 8. Incident Center & Dossier ---")
        nav_to(page, "/incidents")
        save_screenshot(page, "08_incidents_01_list.png", "Incidents - Active Incidents List")

        page.evaluate("window.scrollTo({top: 400, behavior: 'instant'});")
        time.sleep(0.8)
        save_screenshot(page, "08_incidents_02_dossier_detail.png", "Incidents - Dossier Detail & Dispatched Status")
        page.evaluate("window.scrollTo({top: 0, behavior: 'instant'});")

        # ----------------------------------------------------------------------
        # 9. CASE DOSSIER & PDF EXPORT (/cases)
        # ----------------------------------------------------------------------
        print("\n--- 9. Case Dossier & PDF Export ---")
        nav_to(page, "/cases")
        save_screenshot(page, "09_cases_01_dossier_header.png", "Cases - Official Case File Header (CASE-2026-GJ18)")

        page.evaluate("window.scrollTo({top: 450, behavior: 'instant'});")
        time.sleep(0.8)
        save_screenshot(page, "09_cases_02_evidence_gallery.png", "Cases - Evidence Timeline Gallery & Witness Log")
        page.evaluate("window.scrollTo({top: 0, behavior: 'instant'});")

        # ----------------------------------------------------------------------
        # 10. CAMERA RELIABILITY INTELLIGENCE (/cameras)
        # ----------------------------------------------------------------------
        print("\n--- 10. Camera Reliability Intelligence ---")
        nav_to(page, "/cameras")
        save_screenshot(page, "10_cameras_01_health_dashboard.png", "Cameras - Reliability Health Dashboard (99.4% Uptime)")

        page.evaluate("window.scrollTo({top: 400, behavior: 'instant'});")
        time.sleep(0.8)
        save_screenshot(page, "10_cameras_02_diagnostics.png", "Cameras - Blur/Occlusion Alerts & Maintenance Logs")
        page.evaluate("window.scrollTo({top: 0, behavior: 'instant'});")

        # ----------------------------------------------------------------------
        # 11. OPERATIONS, SEARCH & GIS MAP (/map)
        # ----------------------------------------------------------------------
        print("\n--- 11. Operations & GIS Map ---")
        nav_to(page, "/map")
        save_screenshot(page, "11_gis_map_01_fullscreen.png", "GIS Map - Fullscreen Interactive Spatial Map")

        # ----------------------------------------------------------------------
        # 12. SYSTEM SECURITY AUDIT (/system)
        # ----------------------------------------------------------------------
        print("\n--- 12. System Security Audit ---")
        nav_to(page, "/system")
        save_screenshot(page, "12_system_01_health.png", "System - PostGIS Database Health & API Latency")

        page.evaluate("window.scrollTo({top: 400, behavior: 'instant'});")
        time.sleep(0.8)
        save_screenshot(page, "12_system_02_audit_trail.png", "System - Cryptographic Audit Trail Stream")

        context.close()
        browser.close()

    print("\n=== SCREENSHOT CAPTURE COMPLETE! Saved to ./screenshots/ and ./screen_shot/ ===")

if __name__ == "__main__":
    run_screenshot_suite()

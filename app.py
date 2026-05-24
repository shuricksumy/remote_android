import multiprocessing
import subprocess
import sys
import time
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse
import uiautomator2 as u2
import upnpclient

# ==============================================================================
# 1. CONFIGURATION & TARGETS
# ==============================================================================
DEVICE_IP = "192.168.111.48:5555"
PACKAGE_NAME = "com.extreamsd.usbaudioplayerpro"
GLOBAL_TIMEOUT = 10.0

# Name of the active UAPP renderer as seen on the network subnet
UPNP_FRIENDLY_NAME = "MI Player"

# Initialize FastAPI App
app = FastAPI(title="UAPP Web API Service")


# ==============================================================================
# 2. NETWORK & DEVICE CONNECTIVITY ACTIONS
# ==============================================================================
def is_renderer_active_on_network(target_name, retries=3):
    """
    Scans the local network for an active UPnP renderer matching target_name.
    Implements a multi-pass loop to combat UDP/SSDP packet drop over Wi-Fi.
    """
    print(f"🛰️  Network Scan: Checking if service matching '{target_name}' is alive...")

    for attempt in range(1, retries + 1):
        try:
            # discover() parameters:
            # - timeout: seconds to wait for network responses
            # - HTTP_TIMEOUT: socket read thresholds
            devices = upnpclient.discover(timeout=2)

            for device in devices:
                # Keep your debug line to see incoming traffic live
                print(
                    f"️⚠️ DEBUG Network Check [Attempt {attempt}]: Found active broadcast -> '{device.friendly_name}'!")

                if target_name.lower() in device.friendly_name.lower():
                    print(f"🟢 Network Check: Confirmed online -> '{device.friendly_name}'!")
                    return True

        except Exception as e:
            print(f"⚠️ Network scan temporary error on pass {attempt}: {e}")

        # If we didn't find it on this pass, wait a moment for the network buffer to clear
        if attempt < retries:
            time.sleep(0.5)

    print(f"🔴 Network Check: UPnP service was NOT detected after {retries} network sweeps.")
    return False


def initialize_device(ip_address):
    """Ensures raw network ADB is connected, then initializes the uiautomator2 driver."""
    print(f"📡 Step 0: Pinging wireless ADB target at {ip_address}...")
    subprocess.run(f"adb connect {ip_address}", shell=True, capture_output=True)
    time.sleep(1.5)

    try:
        device_inst = u2.connect(ip_address)
        print(
            f"✅ Connection successful! Device Model: {device_inst.info.get('model', 'Unknown')}"
        )
        return device_inst
    except Exception as e:
        print(f"❌ Device connection critical failure: {e}")
        return None


# ==============================================================================
# 3. BACKGROUND SYSTEM DIALOG HANDLER
# ==============================================================================
def background_popup_watcher(ip_address, stop_event):
    """
    Runs in a completely separate process. Constantly scans the
    screen for the system 'Access USB device' dialog text.
    """
    print("👀 [PopupWatcher] Starting background watcher...")

    try:
        watcher_d = u2.connect(ip_address)
    except Exception:
        print("❌ [PopupWatcher] FAILED to connect to device. Watcher exiting.")
        return

    while not stop_event.is_set():
        system_popup_ok = watcher_d(textMatches="(?i)(OK|Allow|Grant)")
        access_context = watcher_d(textContains="access")

        if access_context.exists(timeout=0.1) and system_popup_ok.exists(timeout=0.1):
            print("🚨 [PopupWatcher] CRITICAL POPUP DETECTED!")

            always_checkbox = watcher_d(textMatches="(?i)(Always open)")
            if always_checkbox.exists and not always_checkbox.info.get('checked'):
                print("   ☑️ Setting 'Always open' as default...")
                always_checkbox.click()
                time.sleep(0.5)

            print("   👉 Clicking 'OK' to dismiss system hardware alert.")
            system_popup_ok.click()
            time.sleep(1)

        time.sleep(0.5)

    print("🛑 [PopupWatcher] Watcher process stopping.")


# ==============================================================================
# 4. REUSABLE AUTOMATION ACTION BLOCKS
# ==============================================================================
def launch_fresh_app(device, pkg):
    """Brings app to front if running, otherwise starts normally (doesn't wipe audio)."""
    current_app = device.app_current()
    if current_app.get('package') == pkg:
        print(f"ℹ️ App {pkg} is already open and in focus.")
        return
    print(f"🚀 Bringing {pkg} to the foreground...")
    device.app_start(pkg, stop=False)
    time.sleep(2)


def start_upnp_renderer_from_drawer(device):
    """Opens app sidebar drawer, scrolls, and hits start button."""
    print("🍔 Step 3: Navigating app UI to start the UPnP Renderer...")
    time.sleep(1.0)
    press_system_back(device)
    device.click(0.05, 0.05)
    time.sleep(1.0)

    print("📜 Scrolling side drawer menu down...")
    device.swipe(200, 800, 200, 300, steps=10)
    time.sleep(0.5)

    target_btn = device(text="Start UPnP renderer")
    if target_btn.wait(timeout=GLOBAL_TIMEOUT):
        print("🎯 Element found! Clicking 'Start UPnP renderer'...")
        target_btn.click()
        return True

    raise TimeoutError("Could not locate the 'Start UPnP renderer' button.")


def take_test_screenshot(device, filename="test_result.png"):
    """Saves a current frame of the screen layout for visual verification."""
    print(f"📸 Capturing visual validation state to '{filename}'...")
    device.screenshot(filename)


def return_to_home_page(device):
    """Opens drawer and clicks 'Library' to return to main view."""
    print("🏠 Navigating back to the home view (Library)...")
    device.click(0.05, 0.05)
    time.sleep(1.0)
    home_btn = device(text="Library")
    if home_btn.wait(timeout=5.0):
        home_btn.click()
        print("✅ Returned to Home successfully.")


def press_system_back(device):
    device.press("back")
    time.sleep(0.5)


def press_system_home(device):
    device.press("home")
    time.sleep(1)


def reboot_android_device(device):
    print("🔄 Sending hardware REBOOT command to the device...")
    device.shell("reboot")
    print("💤 Connection dropped. Device is now restarting.")


# ==============================================================================
# 5. CORE AUTOMATION WORKFLOW PIPELINE
# ==============================================================================
def master_automation_pipeline():
    """Runs your full original pipeline logic cleanly in the background."""
    print("\n=== STARTING ROBUST NETWORK-SMART AUTOMATION RUN ===")

    # 🚀 PRIMACY CHECK
    if is_renderer_active_on_network(UPNP_FRIENDLY_NAME):
        print("✨ UPnP service is already running on the Wi-Fi. Script exiting cleanly!")
        print("=== AUTOMATION RUN FINISHED (SKIPPED) ===\n")
        return

    print("\n🛠️ Service undetected. Initializing ADB UI workflow with background popup watcher...")

    # Step 0: Hook main device connection
    d = initialize_device(DEVICE_IP)
    if d is None:
        print("❌ Pipeline stopped due to connection failure.")
        return

    # Start background process watcher
    stop_watcher_event = multiprocessing.Event()
    watcher_process = multiprocessing.Process(
        target=background_popup_watcher,
        args=(DEVICE_IP, stop_watcher_event)
    )
    watcher_process.start()
    time.sleep(1)

    try:
        # Step 1: Initialize App state
        press_system_home(d)
        launch_fresh_app(d, PACKAGE_NAME)

        # Step 2: Navigate UI & Trigger Feature
        start_upnp_renderer_from_drawer(d)

        # Step 3: Clean up screen state
        press_system_back(d)
        press_system_home(d)

        # Step 4: Verification
        print("\n⏳ Waiting 4 seconds for network service broadcast initialization...")
        time.sleep(4)
        if is_renderer_active_on_network(UPNP_FRIENDLY_NAME):
            print("\n🎉 SUCCESS: All steps executed and service verified on network!")
            take_test_screenshot(d, "uapp_automation_success.png")
        else:
            print("\n⚠️ UI macro finished, but the network service is still not broadcasting.")
            take_test_screenshot(d, "uapp_automation_unverified_network.png")

    except Exception as error:
        print(f"\n❌ TEST RUN FAILED at a critical step: {error}")
        take_test_screenshot(d, "uapp_automation_error_dump.png")

    finally:
        print("\n🧹 Shutting down background watcher process...")
        stop_watcher_event.set()
        watcher_process.join(timeout=3)
        if watcher_process.is_alive():
            watcher_process.terminate()

        print("=== TEST RUN PIPELINE FINISHED ===\n")


# ==============================================================================
# 6. HTTP API ENDPOINTS
# ==============================================================================
@app.get("/status")
def get_status():
    """Quickly check network state without opening ADB."""
    active = is_renderer_active_on_network(UPNP_FRIENDLY_NAME)
    return {
        "upnp_service_active": active,
        "friendly_name_target": UPNP_FRIENDLY_NAME,
        "status": "RUNNING" if active else "STOPPED"
    }


@app.post("/trigger")
def trigger_test(background_tasks: BackgroundTasks):
    """Triggers the pipeline as an asynchronous background task."""
    background_tasks.add_task(master_automation_pipeline)
    return {
        "message": "Automation worker triggered",
        "detail": "Checking network. Will engage ADB interface if service is missing."
    }

@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("index.html") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    # Runs the API server on local port 8000
    uvicorn.run(app, host="0.0.0.0", port=8833)
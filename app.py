import contextlib
import multiprocessing
import subprocess
import time
import threading
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
import uiautomator2 as u2
import upnpclient

# ==============================================================================
# 1. CONFIGURATION & TARGETS
# ==============================================================================
DEVICE_IP = "192.168.111.48:5555"
PACKAGE_NAME = "com.extreamsd.usbaudioplayerpro"
GLOBAL_TIMEOUT = 10.0
UPNP_FRIENDLY_NAME = "MI Player"


# ==============================================================================
# 2. LIFESPAN SYSTEM SCHEDULER
# ==============================================================================
def cron_worker_loop(stop_event: threading.Event):
    """Runs a non-blocking background loop checking network state every 10 minutes."""
    print("⏰ Periodic background cron loop initialized.")
    counter = 0
    while not stop_event.is_set():
        if counter <= 0:
            print("⏰ Cron Trigger: Initiating scheduled 10-minute automation pass...")
            try:
                master_automation_pipeline()
            except Exception as e:
                print(f"❌ Scheduled periodic pass encountered an error: {e}")
            counter = 600  # Reset timer to 10 minutes (600 seconds)

        time.sleep(1)
        counter -= 1
    print("🛑 Scheduled periodic background cron worker loop gracefully stopped.")


@contextlib.asynccontextmanager
async def lifespan(app_inst: FastAPI):
    """Handles startup background thread spawning and clean shutdown logic."""
    stop_cron_signal = threading.Event()
    cron_thread = threading.Thread(target=cron_worker_loop, args=(stop_cron_signal,), daemon=True)
    cron_thread.start()

    yield  # Web API server is active

    print("🧹 FastAPI Lifespan: Shutting down daemon loops...")
    stop_cron_signal.set()
    cron_thread.join(timeout=3)


app = FastAPI(title="UAPP Web API Service", lifespan=lifespan)


# ==============================================================================
# 3. NETWORK & ADB CONNECTIVITY ACTIONS
# ==============================================================================
def is_renderer_active_on_network(target_name, retries=3):
    """Scans local Wi-Fi for UPnP renderers with a multi-pass sweep for UDP stability."""
    print(f"🛰️  Network Scan: Checking if service matching '{target_name}' is alive...")
    for attempt in range(1, retries + 1):
        try:
            devices = upnpclient.discover(timeout=2)
            for device in devices:
                print(
                    f"⚠️ DEBUG Network Check [Attempt {attempt}]: Found active broadcast -> '{device.friendly_name}'!")
                if target_name.lower() in device.friendly_name.lower():
                    print(f"🟢 Network Check: Confirmed online -> '{device.friendly_name}'!")
                    return True
        except Exception as e:
            print(f"⚠️ Network scan temporary error on pass {attempt}: {e}")
        if attempt < retries:
            time.sleep(0.5)
    print(f"🔴 Network Check: UPnP service was NOT detected after {retries} network sweeps.")
    return False


def initialize_device(ip_address):
    """Pings raw wireless ADB node and handles driver hook attachment."""
    print(f"📡 Hooking wireless ADB target at {ip_address}...")
    subprocess.run(f"adb connect {ip_address}", shell=True, capture_output=True)
    time.sleep(1.5)
    try:
        device_inst = u2.connect(ip_address)
        print(f"✅ Connection successful! Device Model: {device_inst.info.get('model', 'Unknown')}")
        return device_inst
    except Exception as e:
        print(f"❌ Device connection critical failure: {e}")
        return None


# ==============================================================================
# 4. MULTIPROCESSED ASYNC SYSTEM DIALOG WATCHER
# ==============================================================================
def background_popup_watcher(ip_address, stop_event):
    """Scans the screen interface concurrently to suppress hardware access prompts."""
    print("👀 [PopupWatcher] Starting background watcher...")
    try:
        watcher_d = u2.connect(ip_address)
    except Exception:
        print("❌ [PopupWatcher] FAILED to connect to device. Watcher exiting.")
        return

    while not stop_event.is_set():
        try:
            system_popup_ok = watcher_d(textMatches="(?i)(OK|Allow|Grant)")
            access_context = watcher_d(textContains="access")

            if access_context.exists(timeout=0.1) and system_popup_ok.exists(timeout=0.1):
                print("🚨 [PopupWatcher] CRITICAL POPUP DETECTED!")
                always_checkbox = watcher_d(textMatches="(?i)(Always open)")
                if always_checkbox.exists(timeout=0.2) and not always_checkbox.info.get('checked', False):
                    print("   ☑️ Setting 'Always open' as default...")
                    always_checkbox.click()
                    time.sleep(0.5)

                print("   👉 Clicking 'OK' to dismiss system hardware alert.")
                if system_popup_ok.exists(timeout=0.2):
                    system_popup_ok.click()
                    time.sleep(1)
        except u2.exceptions.UiObjectNotFoundError:
            print("⚠️ [PopupWatcher] Element became unavailable during targeted click frame. Retrying...")
        except Exception as loop_err:
            print(f"⚠️ [PopupWatcher] Ongoing layout sweep warning: {loop_err}")
        time.sleep(0.5)
    print("🛑 [PopupWatcher] Watcher process stopping.")


# ==============================================================================
# 5. REUSABLE AUTOMATION ACTION BLOCKS
# ==============================================================================
def launch_fresh_app(device, pkg):
    """Brings the player to focus safely without resetting current audio streams."""
    current_app = device.app_current()
    if current_app.get('package') == pkg:
        print(f"ℹ️ App {pkg} is already open and in focus.")
        return
    print(f"🚀 Bringing {pkg} to the foreground...")
    device.app_start(pkg, stop=False)
    time.sleep(2)


def start_upnp_renderer_from_drawer(device):
    """Navigates side navigation panel elements to activate streaming server."""
    print("🍔 Toggling sidebar layout navigation...")
    press_system_back(device)
    time.sleep(1.0)
    device.click(0.05, 0.05)
    time.sleep(1.0)

    print("📜 Scrolling side drawer menu down...")
    device.swipe(200, 800, 200, 300, steps=10)
    time.sleep(0.5)

    target_btn = device(text="Start UPnP renderer")
    if target_btn.wait(timeout=GLOBAL_TIMEOUT):
        print("🎯 Element found! Clicking 'Start UPnP renderer'...")
        target_btn.click()
        time.sleep(1)
        press_system_back(device)
        return True
    raise TimeoutError("Could not locate the 'Start UPnP renderer' button.")


def click_app_bottom_home(device):
    """Taps the lower application home area using fixed relative screen geometry."""
    print("🏠 Tapping the application's bottom Home nav icon...")
    device.click(0.11, 0.87)
    time.sleep(1)
    return True


def take_test_screenshot(device, filename="test_result.png"):
    """Saves visual reference frame data to local workspace disk directory."""
    print(f"📸 Capturing visual validation state to '{filename}'...")
    device.screenshot(filename)


def press_system_back(device):
    device.press("back")
    time.sleep(0.5)


def press_system_home(device):
    device.press("home")
    time.sleep(1)


def reboot_android_device():
    """Forces hardware power cycling using decoupled sub-shell interface calls."""
    print("🔄 Sending hardware REBOOT command to the device...")
    try:
        subprocess.run(f"adb -s {DEVICE_IP} reboot", shell=True, capture_output=True, timeout=5)
        print("💤 Reboot command dispatched cleanly via raw ADB interface.")
    except subprocess.TimeoutExpired:
        print("💤 Raw ADB connection timed out intentionally as the hardware shut down.")
    except Exception:
        print("💤 Shell dropped interface attachment. System is now restarting.")


# ==============================================================================
# 6. STEP-BY-STEP CONTROL AUTOMATION WORKFLOW PIPELINE
# ==============================================================================
def master_automation_pipeline():
    """Executes the macro control sequence sequentially with integrated error handlers."""
    print("\n=== STARTING ROBUST NETWORK-SMART AUTOMATION RUN ===")

    # --------------------------------------------------------------------------
    # STEP 1: PRIMACY PRE-FLIGHT NETWORK CHECK
    # --------------------------------------------------------------------------
    # Query network state before sending commands. If online, skip macro entirely.
    if is_renderer_active_on_network(UPNP_FRIENDLY_NAME):
        print("✨ UPnP service is already running on the Wi-Fi. Script exiting cleanly!")
        print("=== AUTOMATION RUN FINISHED (SKIPPED) ===\n")
        return

    print("\n🛠️ Service undetected. Initializing ADB UI workflow with background popup watcher...")

    # --------------------------------------------------------------------------
    # STEP 2: ADB CONNECTION ATTACHMENT
    # --------------------------------------------------------------------------
    # Initialize connection handle with hardware client.
    d = initialize_device(DEVICE_IP)
    if d is None:
        print("❌ Pipeline stopped due to connection failure.")
        return

    # --------------------------------------------------------------------------
    # STEP 3: CONCURRENT SYSTEM POPUP WATCHER LAUNCH
    # --------------------------------------------------------------------------
    # Spawn the safe dialogue listener process in parallel to clear USB prompts.
    stop_watcher_event = multiprocessing.Event()
    watcher_process = multiprocessing.Process(target=background_popup_watcher, args=(DEVICE_IP, stop_watcher_event))
    watcher_process.start()
    time.sleep(1)

    try:
        # ----------------------------------------------------------------------
        # STEP 4: APP LAYER INITIALIZATION
        # ----------------------------------------------------------------------
        # Clear external screen obstructions and open the targeted player bundle.
        press_system_home(d)
        launch_fresh_app(d, PACKAGE_NAME)
        time.sleep(3.0)

        # ----------------------------------------------------------------------
        # STEP 5: NAVIGATION MACRO ROUTINE
        # ----------------------------------------------------------------------
        # Engage UI layout sequences to kickstart internal streaming protocols.
        start_upnp_renderer_from_drawer(d)
        click_app_bottom_home(d)

        # ----------------------------------------------------------------------
        # STEP 6: DYNAMIC ACTIVE VERIFICATION POLLING
        # ----------------------------------------------------------------------
        # Cycle network queries aggressively rather than using fixed sleep calls.
        print("\n🛰️ Engaging active network polling tracker...")
        max_wait, poll_interval, elapsed, service_verified = 10.0, 0.5, 0.0, False

        while elapsed < max_wait:
            if is_renderer_active_on_network(UPNP_FRIENDLY_NAME, retries=1):
                service_verified = True
                print(f"⚡ [Tracker] Service captured online after {elapsed:.1f} seconds! Breaking loop early.")
                break
            time.sleep(poll_interval)
            elapsed += poll_interval

        # ----------------------------------------------------------------------
        # STEP 7: STATE CAPTURE & DISK VALIDATION
        # ----------------------------------------------------------------------
        # Write validation outcomes and frame dumps directly to local folder tree.
        if service_verified:
            print("\n🎉 SUCCESS: All steps executed and service verified active on network!")
            take_test_screenshot(d, "uapp_automation_success.png")
        else:
            print(f"\n⚠️ UI macro finished, but network service failed to broadcast within {max_wait}s.")
            take_test_screenshot(d, "uapp_automation_unverified_network.png")

    except Exception as error:
        print(f"\n❌ TEST RUN FAILED at a critical step: {error}")
        take_test_screenshot(d, "uapp_automation_error_dump.png")

    finally:
        # ----------------------------------------------------------------------
        # STEP 8: REAPER CLEANUP
        # ----------------------------------------------------------------------

        # 🚀 ADDED: Put the display to sleep immediately after finalizing clicks
        print("💤 Macro sequence completed. Turning screen off...")
        d.screen_off()

        # Terminate background listener workers safely to release hardware allocations.
        print("\n🧹 Shutting down background watcher process...")
        stop_watcher_event.set()
        watcher_process.join(timeout=3)
        if watcher_process.is_alive():
            watcher_process.terminate()
        print("=== TEST RUN PIPELINE FINISHED ===\n")


# ==============================================================================
# 7. HTTP API ENDPOINTS
# ==============================================================================
@app.get("/status")
def get_status():
    active = is_renderer_active_on_network(UPNP_FRIENDLY_NAME)
    return {
        "upnp_service_active": active,
        "friendly_name_target": UPNP_FRIENDLY_NAME,
        "status": "RUNNING" if active else "STOPPED"
    }


@app.post("/trigger")
def trigger_test(background_tasks: BackgroundTasks):
    background_tasks.add_task(master_automation_pipeline)
    return {
        "message": "Automation worker triggered",
        "detail": "Checking network. Will engage ADB interface if service is missing."
    }


@app.post("/reboot")
def trigger_device_reboot(background_tasks: BackgroundTasks):
    def perform_reboot():
        print("\n🔄 [API Request] Initiating manual device reboot hook...")
        reboot_android_device()

    background_tasks.add_task(perform_reboot)
    return {
        "message": "Reboot instruction successfully dispatched",
        "detail": "The phone connection will drop momentarily as hardware cycling begins."
    }

@app.get("/screenshot")
def get_live_screenshot():
    """Captures a real-time static frame from the phone and transmits it to the UI client."""
    print("📸 [API Request] Capturing dynamic workspace screenshot for browser dashboard...")
    d_inst = initialize_device(DEVICE_IP)
    if d_inst:
        filename = "live_panel_feed.png"
        d_inst.screenshot(filename)
        return FileResponse(filename, media_type="image/png")
    return {"error": "Could not connect to device over ADB to generate frame profile."}


@app.post("/lock")
def trigger_device_lock(background_tasks: BackgroundTasks):
    """Simulates pressing the physical power button to toggle or lock the screen."""

    def perform_lock():
        print("\n🔒 [API Request] Initiating manual device screen lock hook...")
        d_inst = initialize_device(DEVICE_IP)
        if d_inst:
            print("🔒 Sending system power key event (KeyCode 26)...")
            d_inst.press("power")  # Simulates physical power button tap
        else:
            print("❌ [API Request] Lock action aborted: Could not establish ADB bridge link.")

    background_tasks.add_task(perform_lock)
    return {
        "message": "Screen toggle instruction successfully dispatched",
        "detail": "Power key state signal sent over ADB interface layer."
    }

@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("index.html") as f:
        return f.read()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8833)
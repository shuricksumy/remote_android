import contextlib
import multiprocessing
import subprocess
import time
import os
import threading
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
import uiautomator2 as u2
import upnpclient

# ==============================================================================
# 1. CONFIGURATION & TARGETS
# ==============================================================================
DEVICE_IP = os.environ.get("DEVICE_IP", "192.168.111.48:5555")
PACKAGE_NAME = "com.extreamsd.usbaudioplayerpro"
GLOBAL_TIMEOUT = 10.0
UPNP_FRIENDLY_NAME = "MI Player"

# Global pointer handle to track the live websocket streamer sub-process matrix
WSSCRCPY_PROCESS = None


# ==============================================================================
# 2. LIFESPAN SYSTEM SCHEDULER & STREAM ENGINE DISPATCHER
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
    """Handles startup background thread spawning and explicit ws-scrcpy process attachment."""

@contextlib.asynccontextmanager
async def lifespan(app_inst: FastAPI):
    """Handles startup background thread spawning and explicit ws-scrcpy process attachment."""

    global WSSCRCPY_PROCESS

    # 🚀 STEP 1: Spawning headless web socket streaming canvas via clean shell pass
    print("🚀 Lifespan Initialization: Spawning background ws-scrcpy stream daemon...")
    try:
        # Running via shell=True tells the OS layer to process the global compose environment variable natively
        WSSCRCPY_PROCESS = subprocess.Popen(
            "node /opt/ws-scrcpy/dist/index.js",
            shell=True,
            stdout=None,
            stderr=None
        )
        print("🟢 ws-scrcpy live streaming mirror server spawned successfully.")
    except Exception as launch_err:
        print(f"❌ Failed to spin up the ws-scrcpy socket interface subsystem layer: {launch_err}")

    # STEP 2: Deploying automated background routine checking loops
    stop_cron_signal = threading.Event()
    cron_thread = threading.Thread(target=cron_worker_loop, args=(stop_cron_signal,), daemon=True)
    cron_thread.start()

    yield  # Web API server is active and fully bound to network sockets

    # 🧹 STEP 3: Handle shutdown routines to prevent lingering background zombie workers
    print("🧹 FastAPI Lifespan: Shutting down daemon loops and stream wrappers...")
    stop_cron_signal.set()
    cron_thread.join(timeout=3)

    if WSSCRCPY_PROCESS and WSSCRCPY_PROCESS.poll() is None:
        print("🛑 Terminating active background ws-scrcpy streaming pipe processes...")
        WSSCRCPY_PROCESS.terminate()
        try:
            WSSCRCPY_PROCESS.wait(timeout=2)
            print("✨ Mirror engine closed out clean.")
        except subprocess.TimeoutExpired:
            WSSCRCPY_PROCESS.kill()
            print("💥 Force-killed unresponsive stream framework.")

app = FastAPI(title="UAPP Web API Service", lifespan=lifespan)


# ==============================================================================
# 3. NETWORK & ADB CONNECTIVITY ACTIONS
# ==============================================================================
def is_renderer_active_on_network(target_name, retries=3):
    """Scans local Wi-Fi for UPnP renderers using standard multicast sweeps."""
    print(f"🛰️  Multicast Network Scan: Running network discovery sweep...")
    for attempt in range(1, retries + 1):
        try:
            devices = upnpclient.discover(timeout=1.5)
            for device in devices:
                print(
                    f"⚠️ DEBUG Network Check [Attempt {attempt}]: Found active broadcast -> '{device.friendly_name}'!")
                if target_name.lower() in device.friendly_name.lower():
                    print(f"🟢 Broadcast Check: Confirmed online -> '{device.friendly_name}'!")
                    return True
        except Exception as e:
            print(f"⚠️ Network scan temporary warning on pass {attempt}: {e}")
        if attempt < retries:
            time.sleep(0.3)
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
    # STEP 1: ADB CONNECTION ATTACHMENT
    # --------------------------------------------------------------------------
    d = initialize_device(DEVICE_IP)
    if d is None:
        print("❌ Pipeline stopped due to connection failure.")
        return

    # Track screen status so we know whether to put it back to sleep at the very end
    started_asleep = not d.info.get("screenOn", False)

    # --------------------------------------------------------------------------
    # STEP 2: MANDATORY PRE-FLIGHT AWAKE STRATEGY
    # --------------------------------------------------------------------------
    if started_asleep:
        print("💤 Display is currently asleep. Waking up screen layout for verification...")
        d.press("power")
        time.sleep(1.0)
        print("🔓 Dismissing lock screen layer via swipe gesture...")
        d.swipe(0.5, 0.8, 0.5, 0.2, duration=0.3)
        time.sleep(1.5)

    # --------------------------------------------------------------------------
    # STEP 3: PRIMACY RUNNING SERVICE SCAN
    # --------------------------------------------------------------------------
    if is_renderer_active_on_network(UPNP_FRIENDLY_NAME):
        print("✨ UPnP service is already running on the Wi-Fi. Script exiting cleanly!")
        if started_asleep:
            print("💤 Locking screen back to original sleep configuration...")
            d.press("power")
        print("=== AUTOMATION RUN FINISHED (SKIPPED) ===\n")
        return

    print("\n🛠️ Service undetected. Initializing UI macro loop sequence...")

    # --------------------------------------------------------------------------
    # STEP 4: CONCURRENT SYSTEM POPUP WATCHER LAUNCH
    # --------------------------------------------------------------------------
    stop_watcher_event = multiprocessing.Event()
    watcher_process = multiprocessing.Process(target=background_popup_watcher, args=(DEVICE_IP, stop_watcher_event))
    watcher_process.start()
    time.sleep(1)

    try:
        # ----------------------------------------------------------------------
        # STEP 5: APP LAYER INITIALIZATION
        # ----------------------------------------------------------------------
        press_system_home(d)
        launch_fresh_app(d, PACKAGE_NAME)
        time.sleep(3.0)

        # ----------------------------------------------------------------------
        # STEP 6: NAVIGATION MACRO ROUTINE
        # ----------------------------------------------------------------------
        start_upnp_renderer_from_drawer(d)
        click_app_bottom_home(d)

        # ----------------------------------------------------------------------
        # STEP 7: DYNAMIC ACTIVE VERIFICATION POLLING
        # ----------------------------------------------------------------------
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
        # STEP 8: STATE CAPTURE & DISK VALIDATION
        # ----------------------------------------------------------------------
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
        if started_asleep:
            print("💤 Locking screen back to original sleep configuration...")
            d.press("power")

        # ----------------------------------------------------------------------
        # STEP 9: REAPER CLEANUP
        # ----------------------------------------------------------------------
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
    """Wakes the network table up if phone is sleeping, checks status, then restores sleep state."""
    d_inst = initialize_device(DEVICE_IP)
    if not d_inst:
        return {"upnp_service_active": False, "friendly_name_target": UPNP_FRIENDLY_NAME, "status": "STOPPED"}

    started_asleep = not d_inst.info.get("screenOn", False)

    if started_asleep:
        print("💤 [API Status] Screen is dark. Temporarily waking device to refresh routing table...")
        d_inst.press("power")
        time.sleep(1.0)
        d_inst.swipe(0.5, 0.8, 0.5, 0.2, duration=0.3)
        time.sleep(1.5)

    active = is_renderer_active_on_network(UPNP_FRIENDLY_NAME)

    if started_asleep:
        print("💤 [API Status] Restoring dark screen sleep configuration...")
        d_inst.press("power")

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
        "detail": "Engaging secure wake, check, and restore execution loop."
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
    """Guarantees the screen is locked/turned off. Only hits the power key if screen is ON."""

    def perform_lock():
        print("\n🔒 [API Request] Initiating manual device screen lock hook...")
        d_inst = initialize_device(DEVICE_IP)
        if d_inst:
            if d_inst.info.get("screenOn", True):
                print("🔒 Screen is currently ON. Sending power key event (KeyCode 26) to lock...")
                d_inst.press("power")
            else:
                print("ℹ️ Screen is already dark and locked. Command skipped to prevent toggling.")
        else:
            print("❌ [API Request] Lock action aborted: Could not establish ADB bridge link.")

    background_tasks.add_task(perform_lock)
    return {
        "message": "Lock instruction successfully processed",
        "detail": "Display validation pass dispatched over ADB interface layer."
    }


@app.post("/unlock")
def trigger_device_unlock(background_tasks: BackgroundTasks):
    """Guarantees the screen is turned on and unlocked. Only hits power and swipe if screen is OFF."""

    def perform_unlock():
        print("\n🔓 [API Request] Initiating manual device screen unlock hook...")
        d_inst = initialize_device(DEVICE_IP)
        if d_inst:
            if not d_inst.info.get("screenOn", False):
                print("💤 Screen is dark. Sending power key event to wake device...")
                d_inst.press("power")
                time.sleep(1.0)
                print("🔓 Dismissing lock screen layer via swipe...")
                d_inst.swipe(0.5, 0.8, 0.5, 0.2, duration=0.3)
            else:
                print("ℹ️ Screen is already illuminated and awake. Command skipped to prevent toggling.")
        else:
            print("❌ [API Request] Unlock action aborted: Could not establish ADB bridge link.")

    background_tasks.add_task(perform_unlock)
    return {
        "message": "Unlock instruction successfully processed",
        "detail": "Wake and drag gesture pass dispatched over ADB interface layer."
    }


@app.post("/restart-app")
def trigger_audio_app_restart(background_tasks: BackgroundTasks):
    """Force-terminates the player application process tree and relaunches it fresh."""

    def perform_app_restart():
        print(f"\n🔄 [API Request] Initiating fresh restart routine for package: {PACKAGE_NAME}")
        d_inst = initialize_device(DEVICE_IP)
        if d_inst:
            print("🛑 Killing active process hooks...")
            d_inst.app_stop(PACKAGE_NAME)
            time.sleep(1.5)

            print("🚀 Relaunching main application window activity layer...")
            d_inst.app_start(PACKAGE_NAME)
            print("🟢 App relaunch sequence processed successfully.")
        else:
            print("❌ [API Request] App restart aborted: ADB device handle unreachable.")

    background_tasks.add_task(perform_app_restart)
    return {
        "message": "App restart sequence successfully triggered",
        "detail": f"Force-stop and launch parameters dispatched for {PACKAGE_NAME}."
    }
@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("index.html") as f:
        html_content = f.read()

    # 🚀 LIVE JAVASCRIPT INJECTION: Swaps out the hardcoded address on load
    clean_ip = DEVICE_IP.split(":")[0]  # Extracts just "192.168.111.48"
    modified_html = html_content.replace(
        'const DEVICE_IP = "192.168.111.48:5555";',
        f'const DEVICE_IP = "{DEVICE_IP}";'
    )
    return modified_html


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8833)
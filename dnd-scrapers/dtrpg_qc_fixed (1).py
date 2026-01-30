import os
import time
import shutil
import hashlib
import threading
import subprocess
import random
from pathlib import Path
from queue import Queue, Empty

import tkinter as tk
from tkinter import ttk, filedialog

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    WebDriverException,
    TimeoutException,
    SessionNotCreatedException,
)

# -----------------------------
# Optional notifications
# -----------------------------
try:
    from plyer import notification
    PLYER_AVAILABLE = True
except Exception:
    PLYER_AVAILABLE = False

# -----------------------------
# Paths / constants
# -----------------------------
USER_HOME = Path(os.environ.get("DTRPG_USER_HOME", str(Path.home())))
AUTO_PROFILE_PATH = USER_HOME / ".config/google-chrome-automation"
DEFAULT_STORAGE = USER_HOME / "Documents/DTRPG_QC_Project"
CART_LIMIT = 50
MAX_PAGES_DEFAULT = 50


def which_chrome() -> str:
    for p in ["/usr/bin/google-chrome-stable", "/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium"]:
        if Path(p).exists():
            return p
    for name in ["google-chrome-stable", "google-chrome", "chromium-browser", "chromium"]:
        p = shutil.which(name)
        if p:
            return p
    return "/usr/bin/google-chrome"


CHROME_BIN = which_chrome()


def detect_chrome_major(default=0) -> int:
    try:
        out = subprocess.check_output([CHROME_BIN, "--version"], text=True).strip()
        # ex: "Google Chrome 144.0.7559.109"
        for token in out.split():
            if token and token[0].isdigit() and "." in token:
                return int(token.split(".")[0])
    except Exception:
        pass
    return default


def is_invalid_session(exc: Exception) -> bool:
    s = str(exc).lower()
    return (
        "invalid session id" in s
        or "session deleted because of page crash" in s
        or "chrome not reachable" in s
        or "disconnected" in s
    )


def chrome_using_profile(profile_dir: Path) -> bool:
    # Chrome uses SingletonLock / SingletonCookie / SingletonSocket
    for name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        if (profile_dir / name).exists():
            return True
    return False


def cleanup_profile_locks(profile_dir: Path):
    for name in ["SingletonLock", "SingletonCookie", "SingletonSocket", "Lockfile"]:
        try:
            (profile_dir / name).unlink(missing_ok=True)
        except Exception:
            pass


class DTRPG_Enterprise_System:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("DTRPG QC — Stable Cart + Library Downloader")
        self.root.geometry("900x780")

        self.uiq: Queue = Queue()
        self.stop_flag = threading.Event()

        self.download_path = tk.StringVar(value=str(DEFAULT_STORAGE))
        self.status_msg = tk.StringVar(value="System Ready")
        self.progress_val = tk.IntVar(value=0)

        self.pass_type = tk.StringVar(value="MANUAL")  # MANUAL or SYNC

        # Toggles
        env_has_creds = bool(os.getenv("DTRPG_EMAIL") and os.getenv("DTRPG_PASSWORD"))
        self.auto_login_var = tk.BooleanVar(value=env_has_creds)
        self.auto_checkout_var = tk.BooleanVar(value=False)
        self.pause_on_fail_var = tk.BooleanVar(value=True)

        # Timing controls (slow + stable defaults)
        self.add_wait_s = tk.DoubleVar(value=4.0)  # increased from 3.0
        self.page_wait_s = tk.DoubleVar(value=7.0)  # increased from 6.0
        self.verify_timeout_s = tk.DoubleVar(value=25.0)  # increased from 22.0
        self.cooldown_every = tk.IntVar(value=5)
        self.cooldown_s = tk.DoubleVar(value=9.0)
        self.max_pages = tk.IntVar(value=MAX_PAGES_DEFAULT)

        self.items_carted = 0
        self.notifications_active = True
        self.seed_list_url = None  # Store the original filtered URL

        self.setup_ui()
        self.root.after(100, self._drain_ui_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # -----------------------------
    # UI helpers
    # -----------------------------
    def _drain_ui_queue(self):
        try:
            while True:
                fn = self.uiq.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
        except Empty:
            pass
        self.root.after(100, self._drain_ui_queue)

    def ui(self, fn):
        self.uiq.put(fn)

    def log(self, message: str):
        ts = time.strftime("%H:%M:%S")

        def _do():
            self.log_box.insert(tk.END, f"[{ts}] {message}\n")
            self.log_box.see(tk.END)

        self.ui(_do)

    def set_progress(self, pct: int):
        self.ui(lambda: self.progress_val.set(int(max(0, min(100, pct)))))

    def set_status(self, s: str):
        self.ui(lambda: self.status_msg.set(s))

    def blocking_modal(self, title: str, msg: str, button_text="Continue"):
        gate = threading.Event()

        def _do():
            try:
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
                self.root.attributes("-topmost", True)
                self.root.after(250, lambda: self.root.attributes("-topmost", False))
            except Exception:
                pass

            win = tk.Toplevel(self.root)
            win.title(title)
            win.transient(self.root)
            win.grab_set()
            try:
                win.attributes("-topmost", True)
            except Exception:
                pass

            frm = ttk.Frame(win, padding=16)
            frm.pack(fill="both", expand=True)

            lbl = ttk.Label(frm, text=msg, justify="left", wraplength=760)
            lbl.pack(fill="both", expand=True)

            def close():
                try:
                    win.grab_release()
                except Exception:
                    pass
                try:
                    win.destroy()
                except Exception:
                    pass
                gate.set()

            btn = ttk.Button(frm, text=button_text, command=close)
            btn.pack(pady=(12, 0))
            win.protocol("WM_DELETE_WINDOW", close)

            win.update_idletasks()
            x = self.root.winfo_rootx() + (self.root.winfo_width() // 2) - (win.winfo_width() // 2)
            y = self.root.winfo_rooty() + (self.root.winfo_height() // 2) - (win.winfo_height() // 2)
            win.geometry(f"+{max(0, x)}+{max(0, y)}")
            btn.focus_set()

        self.ui(_do)
        gate.wait()

    # -----------------------------
    # UI layout
    # -----------------------------
    def setup_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        frame_pass = ttk.LabelFrame(top, text="Mode", padding=10)
        frame_pass.pack(fill="x")

        ttk.Radiobutton(frame_pass, text="Mode A: Manual Filter (Add-to-cart)",
                        variable=self.pass_type, value="MANUAL").pack(side="left", padx=10)
        ttk.Radiobutton(frame_pass, text="Mode B: Library Sync (Download owned)",
                        variable=self.pass_type, value="SYNC").pack(side="left", padx=10)

        frame_dir = ttk.LabelFrame(top, text="Download Folder", padding=10)
        frame_dir.pack(fill="x", pady=(8, 0))
        ttk.Entry(frame_dir, textvariable=self.download_path).pack(side="left", fill="x", expand=True)
        ttk.Button(frame_dir, text="Browse", command=self._browse_dir).pack(side="right")

        frame_opts = ttk.LabelFrame(top, text="Automation Options", padding=10)
        frame_opts.pack(fill="x", pady=(8, 0))

        ttk.Checkbutton(frame_opts, text="Auto-login (uses DTRPG_EMAIL / DTRPG_PASSWORD env vars)",
                        variable=self.auto_login_var).grid(row=0, column=0, sticky="w", padx=6, pady=2)
        ttk.Checkbutton(frame_opts, text="Auto-checkout → Library → Download (after adds / at end)",
                        variable=self.auto_checkout_var).grid(row=1, column=0, sticky="w", padx=6, pady=2)
        ttk.Checkbutton(frame_opts, text="Pause on failures (recommended)",
                        variable=self.pause_on_fail_var).grid(row=2, column=0, sticky="w", padx=6, pady=2)

        frame_tune = ttk.LabelFrame(top, text="Stability Tuning (Slower = more reliable)", padding=10)
        frame_tune.pack(fill="x", pady=(8, 0))

        def add_row(r, label, var):
            ttk.Label(frame_tune, text=label).grid(row=r, column=0, sticky="w", padx=6, pady=2)
            ttk.Entry(frame_tune, textvariable=var, width=10).grid(row=r, column=1, sticky="w", padx=6, pady=2)

        add_row(0, "Add-to-cart wait (sec):", self.add_wait_s)
        add_row(1, "Page change wait (sec):", self.page_wait_s)
        add_row(2, "Verify timeout (sec):", self.verify_timeout_s)
        add_row(3, "Cooldown every N adds:", self.cooldown_every)
        add_row(4, "Cooldown duration (sec):", self.cooldown_s)
        add_row(5, "Max pages to scan:", self.max_pages)

        frame_prog = ttk.LabelFrame(top, text="Progress", padding=10)
        frame_prog.pack(fill="x", pady=(8, 0))
        ttk.Progressbar(frame_prog, variable=self.progress_val, maximum=100).pack(fill="x", pady=4)
        ttk.Label(frame_prog, textvariable=self.status_msg).pack(anchor="w")

        self.log_box = tk.Text(self.root, height=18, bg="#000000", fg="#00FF00", font=("Courier", 10), wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=10, pady=10)

        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(fill="x")

        self.start_btn = ttk.Button(bottom, text="LAUNCH AUTOMATION", command=self.start_thread)
        self.start_btn.pack(side="left")

        self.stop_btn = ttk.Button(bottom, text="STOP", command=self.request_stop)
        self.stop_btn.pack(side="left", padx=10)

        ttk.Label(bottom, text=f"Chrome: {CHROME_BIN}").pack(side="right")

    def _browse_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.download_path.set(d)

    def on_close(self):
        self.request_stop()
        self.root.after(200, self.root.destroy)

    def request_stop(self):
        self.stop_flag.set()
        self.log("STOP: requested by user.")

    # -----------------------------
    # Notifications
    # -----------------------------
    def send_notification(self, title, message):
        if PLYER_AVAILABLE and self.notifications_active:
            try:
                notification.notify(title=title, message=message, app_name="DTRPG QC", timeout=5)
            except Exception as e:
                self.notifications_active = False
                self.log(f"WARN: Notify failed; disabling ({e})")
        else:
            self.log(f"NOTIFY: {title} — {message}")

    # -----------------------------
    # Debug helpers
    # -----------------------------
    def debug_dump(self, driver, tag: str):
        try:
            base = Path(self.download_path.get())
            dbg = base / "_debug"
            dbg.mkdir(parents=True, exist_ok=True)
            driver.save_screenshot(str(dbg / f"{tag}.png"))
            (dbg / f"{tag}.html").write_text(driver.page_source, encoding="utf-8", errors="replace")
            (dbg / f"{tag}.url.txt").write_text(driver.current_url, encoding="utf-8", errors="replace")
            self.log(f"DEBUG: dumped {tag} -> {dbg}")
        except Exception as e:
            self.log(f"DEBUG: dump failed: {e}")

    # -----------------------------
    # Selenium helpers
    # -----------------------------
    def smart_click(self, driver, element):
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
            time.sleep(0.3)
        except Exception:
            pass
        try:
            element.click()
            return "native"
        except Exception:
            pass
        try:
            ActionChains(driver).move_to_element(element).pause(0.15).click(element).perform()
            return "actions"
        except Exception:
            pass
        try:
            driver.execute_script("arguments[0].click();", element)
            return "js"
        except Exception:
            pass
        return "js"

    def is_logged_in(self, driver) -> bool:
        try:
            html = (driver.page_source or "").lower()
            url = (driver.current_url or "").lower()
        except Exception:
            return False
        # Check for logout/account links and NOT on login page
        return (
            (("logoff" in html) or ("my account" in html) or ("/en/library" in html))
            and ("login" not in url or "/login" not in url)
        )

    def guard_interstitial(self, driver, context: str) -> bool:
        """
        STRICT detection: only trigger on REAL Cloudflare/Turnstile challenges.
        Avoid false positives from normal page content.
        """
        try:
            url = driver.current_url or ""
        except Exception:
            url = ""
        url_l = url.lower()

        try:
            title = driver.execute_script("return document.title") or ""
        except Exception:
            title = ""
        title_l = title.lower()

        try:
            html = (driver.page_source or "").lower()
        except Exception:
            html = ""

        # VERY STRICT: Only trigger on actual challenge page elements
        # Not just keywords that might appear in product descriptions
        strong_signals = [
            "cf-browser-verification",  # Cloudflare challenge div
            "challenge-platform",        # Cloudflare challenge
            "cdn-cgi/challenge",         # Cloudflare challenge URL path
            "cf-challenge-running",      # Cloudflare active challenge
        ]
        
        url_signals = [
            "cdn-cgi/challenge",
        ]

        # Title must match exactly (not just contain words)
        title_exact = [
            "just a moment...",
            "just a moment",
            "please wait...",
            "checking your browser",
        ]

        hit = (
            any(sig in html for sig in strong_signals)
            or any(sig in url_l for sig in url_signals)
            or any(title_l.strip() == sig for sig in title_exact)
        )

        if hit:
            self.log(f"GUARD: REAL verification detected ({context}) title='{title}'")
            self.debug_dump(driver, f"interstitial_{context}")
            dbg_dir = str(Path(self.download_path.get()) / "_debug")
            self.blocking_modal(
                "Verification Challenge Detected",
                "A REAL Cloudflare verification was detected.\n\n"
                f"Chrome tab title: {title}\n"
                f"URL: {url}\n\n"
                "Check Chrome - it may be in a background tab.\n"
                f"Screenshot saved to: {dbg_dir}\n\n"
                "Complete the challenge, then click Continue."
            )
            return True

        # Login guard (simple, accurate)
        if "/login" in url_l and not self.is_logged_in(driver):
            self.log(f"GUARD: login required ({context})")
            self.blocking_modal(
                "Login Required",
                "You've been logged out.\n\n"
                "Log in in Chrome, then click Continue."
            )
            return True

        return False

    def get_cart_badge_count(self, driver):
        candidates = [
            (By.CSS_SELECTOR, "#cart_count"),
            (By.CSS_SELECTOR, ".cart-count"),
            (By.CSS_SELECTOR, "a[href*='cart'] .count"),
            (By.CSS_SELECTOR, "a[href*='cart'] span"),
        ]
        for by, sel in candidates:
            try:
                el = driver.find_element(by, sel)
                txt = (el.text or "").strip()
                digits = "".join(c for c in txt if c.isdigit())
                if digits:
                    return int(digits)
            except Exception:
                pass
        return None

    def wait_cart_change(self, driver, before, timeout_s: float):
        """Wait for cart badge to change, indicating successful add"""
        if before is None:
            return None
        end = time.time() + timeout_s
        last_check = before
        while time.time() < end:
            now = self.get_cart_badge_count(driver)
            if now is not None and now != before:
                self.log(f"VERIFY: cart changed {before} → {now}")
                return True
            last_check = now
            time.sleep(0.4)
        self.log(f"VERIFY: timeout - cart stayed at {last_check}")
        return False

    def find_add_to_cart_button(self, driver):
        """Find Add to Cart button with high precision"""
        # Prefer submit inputs with "cart" in value
        xpath = ("//input[@type='submit' and contains(translate(@value,"
                 "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cart')]"
                 "|//button[contains(translate(.,"
                 "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add to cart')]"
                 "|//button[contains(translate(.,"
                 "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'cart')]")
        try:
            els = driver.find_elements(By.XPATH, xpath)
            for el in els:
                try:
                    if el.is_displayed() and el.is_enabled():
                        return el
                except Exception:
                    pass
        except Exception:
            pass
        return None

    def find_next_page_el(self, driver):
        """Find pagination Next link (prefer pagination-specific selectors)"""
        candidates = [
            (By.CSS_SELECTOR, "nav.pagination a[rel='next']"),
            (By.CSS_SELECTOR, "nav.pagination a.next"),
            (By.CSS_SELECTOR, ".pagination a[rel='next']"),
            (By.CSS_SELECTOR, ".pagination a.next"),
            (By.CSS_SELECTOR, "a[rel='next']"),
        ]
        for by, sel in candidates:
            try:
                el = driver.find_element(by, sel)
                if el and el.is_displayed() and el.is_enabled():
                    href = el.get_attribute("href") or ""
                    # Verify it's actually a pagination link (contains page number or filter params)
                    if "?" in href or "page" in href.lower():
                        return el
            except Exception:
                pass

        # Last resort: visible "Next" link inside pagination container
        try:
            els = driver.find_elements(By.XPATH, 
                "//nav[@class='pagination']//a[contains(translate(., 'NEXT', 'next'),'next')]"
                "|//*[contains(@class,'pagination')]//a[contains(translate(., 'NEXT', 'next'),'next')]")
            for el in els:
                try:
                    if el.is_displayed() and el.is_enabled():
                        return el
                except Exception:
                    pass
        except Exception:
            pass
        return None

    # -----------------------------
    # Login automation
    # -----------------------------
    def try_auto_login(self, driver, wait) -> bool:
        """Auto-login using environment variables"""
        email = os.getenv("DTRPG_EMAIL", "").strip()
        pw = os.getenv("DTRPG_PASSWORD", "").strip()
        if not (email and pw):
            self.log("AUTOLOGIN: env vars not set; skipping.")
            return False

        self.log("AUTOLOGIN: attempting…")
        driver.get("https://www.drivethrurpg.com/login.php")
        
        # Wait for page load
        try:
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        except Exception:
            pass
        time.sleep(2.0)

        # Check if already logged in
        if self.is_logged_in(driver):
            self.log("AUTOLOGIN: already logged in.")
            return True

        # Handle any interstitial
        if self.guard_interstitial(driver, "autologin_precheck"):
            pass

        # Find email field
        def find_any(selectors):
            for by, sel in selectors:
                try:
                    el = driver.find_element(by, sel)
                    if el and el.is_displayed():
                        return el
                except Exception:
                    pass
            return None

        email_el = find_any([
            (By.NAME, "email_address"),
            (By.ID, "email_address"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.CSS_SELECTOR, "input[name*='email']"),
        ])
        pw_el = find_any([
            (By.NAME, "password"),
            (By.ID, "password"),
            (By.CSS_SELECTOR, "input[type='password']"),
        ])

        if not email_el or not pw_el:
            self.log("AUTOLOGIN: could not locate login fields.")
            self.debug_dump(driver, "autologin_no_fields")
            return False

        # Fill and submit
        try:
            email_el.clear()
            time.sleep(0.2)
            email_el.send_keys(email)
            time.sleep(0.3)
            pw_el.clear()
            time.sleep(0.2)
            pw_el.send_keys(pw)
            time.sleep(0.3)
        except Exception as e:
            self.log(f"AUTOLOGIN: field fill failed: {e}")
            return False

        # Find and click submit
        btn = find_any([
            (By.CSS_SELECTOR, "input[type='submit']"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.XPATH, "//button[contains(translate(., 'LOGIN', 'login'), 'login')]"),
        ])
        
        if btn:
            self.log("AUTOLOGIN: clicking submit button…")
            self.smart_click(driver, btn)
        else:
            self.log("AUTOLOGIN: no button found, trying form submit…")
            try:
                pw_el.submit()
            except Exception:
                pass

        # Wait for login to complete (up to 15 seconds)
        self.log("AUTOLOGIN: waiting for login confirmation…")
        for i in range(60):
            if self.stop_flag.is_set():
                return False
            
            time.sleep(0.25)
            
            # Check if we're logged in and NOT on login page
            if self.is_logged_in(driver):
                curr_url = (driver.current_url or "").lower()
                if "login" not in curr_url:
                    self.log("AUTOLOGIN: ✓ SUCCESS - logged in!")
                    return True
        
        # Timeout
        self.log("AUTOLOGIN: timeout - login may have failed.")
        self.debug_dump(driver, "autologin_timeout")
        return False

    # -----------------------------
    # Chrome start
    # -----------------------------
    def start_driver(self):
        AUTO_PROFILE_PATH.mkdir(parents=True, exist_ok=True)

        if chrome_using_profile(AUTO_PROFILE_PATH):
            self.blocking_modal(
                "Close Chrome",
                f"Chrome is already using this automation profile:\n{AUTO_PROFILE_PATH}\n\n"
                "Close ALL Chrome windows, then click Continue."
            )

        if not chrome_using_profile(AUTO_PROFILE_PATH):
            cleanup_profile_locks(AUTO_PROFILE_PATH)

        major = detect_chrome_major(default=0) or 0
        self.log(f"Chrome detected: major={major} bin={CHROME_BIN}")

        last_err = None
        for attempt in range(1, 4):
            try:
                options = uc.ChromeOptions()
                options.add_argument("--disable-popup-blocking")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--no-first-run")
                options.add_argument("--no-default-browser-check")
                options.add_argument("--disable-features=Translate,BackForwardCache")
                options.add_argument("--no-sandbox")
                options.add_argument(f"--user-data-dir={str(AUTO_PROFILE_PATH)}")

                prefs = {
                    "download.default_directory": self.download_path.get(),
                    "download.prompt_for_download": False,
                    "plugins.always_open_pdf_externally": True,
                }
                options.add_experimental_option("prefs", prefs)

                self.log(f"Starting Chrome (attempt {attempt}/3)…")
                kwargs = dict(
                    options=options,
                    browser_executable_path=CHROME_BIN,
                    port=0,
                )
                if major > 0:
                    kwargs["version_main"] = major

                return uc.Chrome(**kwargs)

            except SessionNotCreatedException as e:
                last_err = e
                msg = str(e)
                self.log(f"Start failed (SessionNotCreated): {msg}")

                # If driver mismatch, purge UC cache and retry
                if "only supports chrome version" in msg.lower():
                    self.log("UC cache mismatch — purging and retrying…")
                    try:
                        shutil.rmtree(str(USER_HOME / ".local/share/undetected_chromedriver"), ignore_errors=True)
                    except Exception:
                        pass
                    major = detect_chrome_major(default=major or 0)
                    time.sleep(1.0)
                    continue

                time.sleep(1.0)

            except Exception as e:
                last_err = e
                self.log(f"Start failed: {e}")
                time.sleep(1.0)

        raise RuntimeError(f"Chrome failed to start after 3 attempts: {last_err}")

    # -----------------------------
    # Thread runner
    # -----------------------------
    def start_thread(self):
        Path(self.download_path.get()).mkdir(parents=True, exist_ok=True)
        self.stop_flag.clear()
        self.start_btn.config(state="disabled")
        threading.Thread(target=self.run_process, daemon=True).start()

    def run_process(self):
        driver = None
        current_pass = self.pass_type.get()
        self.items_carted = 0
        self.seed_list_url = None

        try:
            self.set_status("Starting Chrome…")
            self.log(f"SYSTEM: Mode={current_pass}")

            driver = self.start_driver()
            wait = WebDriverWait(driver, 25)

            # Auto-login if enabled
            self.set_status("Login…")
            if self.auto_login_var.get():
                login_success = self.try_auto_login(driver, wait)
                if not login_success:
                    self.log("AUTOLOGIN: failed or timed out - will prompt for manual login.")

            # Verify logged in
            if not self.is_logged_in(driver):
                self.blocking_modal(
                    "Login Required",
                    "Please login in the Chrome window.\n\n"
                    "After you are logged in, click Continue."
                )

            if self.stop_flag.is_set():
                return

            if current_pass == "SYNC":
                self.set_status("SYNC: Opening library…")
                self.sync_library(driver, wait)
            else:
                self.set_status("MANUAL: Awaiting filtered page…")
                self.blocking_modal(
                    "Ready to Scrape",
                    "1) In Chrome: set your filters (D&D 5e / Free / etc)\n"
                    "2) Make sure you are on the EXACT results page you want scraped\n"
                    "3) Click Continue here\n\n"
                    "The bot will preserve your filter settings throughout the run."
                )
                
                # Lock in the seed URL with current filters
                self.seed_list_url = driver.current_url
                self.log(f"ACQUIRE: Seed URL locked: {self.seed_list_url}")

                self.set_status("ACQUIRE: Running…")
                self.acquire_across_pages(driver, wait)

                if self.auto_checkout_var.get() and not self.stop_flag.is_set():
                    self.checkout_and_download(driver, wait)

        except Exception as e:
            self.log(f"CRITICAL: {e}")
            try:
                if driver:
                    self.debug_dump(driver, "critical_exception")
            except Exception:
                pass
        finally:
            self.set_status("Complete")
            self.send_notification("DTRPG QC", f"{current_pass} run finished.")
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            self.ui(lambda: self.start_btn.config(state="normal"))

    # -----------------------------
    # Mode B: Sync library
    # -----------------------------
    def sync_library(self, driver, wait):
        if self.stop_flag.is_set():
            return

        self.log("SYNC: opening library…")
        driver.get("https://www.drivethrurpg.com/en/library")
        time.sleep(4.0)

        if self.guard_interstitial(driver, "library"):
            pass

        base = Path(self.download_path.get())
        base.mkdir(parents=True, exist_ok=True)

        existing = set()
        for root, _, files in os.walk(base):
            for f in files:
                existing.add(f.lower())

        try:
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        except Exception:
            pass

        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='download_file']")
        self.log(f"SYNC: found {len(links)} download links (best-effort).")

        to_click = []
        for a in links:
            try:
                title = (a.get_attribute("title") or a.text or "").strip()
                clean = title.replace("Download ", "").strip()
                if clean and clean.lower() not in existing:
                    to_click.append(a)
            except Exception:
                pass

        self.log(f"SYNC: {len(to_click)} appear new vs local folder.")
        for i, a in enumerate(to_click, start=1):
            if self.stop_flag.is_set():
                return
            try:
                self.smart_click(driver, a)
                time.sleep(2.0)
            except Exception:
                pass
            self.set_progress(int((i / max(1, len(to_click))) * 100))

    # -----------------------------
    # Mode A: Acquire across pages (PRESERVE FILTERS!)
    # -----------------------------
    def acquire_across_pages(self, driver, wait):
        """
        Carefully navigate pages while preserving filter state.
        Opens products in new tabs to avoid losing the list page.
        """
        add_wait = float(self.add_wait_s.get())
        page_wait = float(self.page_wait_s.get())
        verify_t = float(self.verify_timeout_s.get())
        cd_every = int(self.cooldown_every.get())
        cd_s = float(self.cooldown_s.get())
        max_pages = int(self.max_pages.get())

        page = 0
        adds = 0

        while page < max_pages and not self.stop_flag.is_set():
            page += 1

            # Guard against challenges
            if self.guard_interstitial(driver, f"list_page_{page}"):
                pass

            self.log(f"LIST: scanning page {page}…")
            
            # Wait for page to be ready
            try:
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            except Exception:
                pass
            time.sleep(1.2 + random.random() * 0.8)

            # Collect product URLs from current page
            links = []
            try:
                links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
            except Exception:
                pass

            urls = []
            for el in links:
                try:
                    href = el.get_attribute("href")
                    if href and "/product/" in href:
                        urls.append(href)
                except Exception:
                    pass

            # Dedupe while preserving order
            seen = set()
            urls2 = []
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    urls2.append(u)

            if not urls2:
                self.log("⚠️ WARN: no product links found — filters may be lost!")
                self.debug_dump(driver, f"no_products_page_{page}")
                self.blocking_modal(
                    "No Products Found",
                    "No product links were found on this page.\n\n"
                    "Your filters may have been reset.\n\n"
                    "Please restore your filters in Chrome, then click Continue."
                )
                continue

            self.log(f"LIST: found {len(urls2)} products on page {page}.")
            
            # Save current list state
            list_handle = driver.current_window_handle
            list_url = driver.current_url

            # Process each product
            for i, url in enumerate(urls2, start=1):
                if self.stop_flag.is_set():
                    return

                # Check cart limit
                if self.items_carted >= CART_LIMIT:
                    self.log("CART: reached limit (50).")
                    if self.auto_checkout_var.get():
                        self.checkout_and_download(driver, wait)
                        self.items_carted = 0
                        
                        # After checkout, MUST restore filter page
                        if self.seed_list_url:
                            self.log(f"RESTORE: returning to seed URL: {self.seed_list_url}")
                            driver.get(self.seed_list_url)
                            time.sleep(page_wait)
                            list_url = driver.current_url
                        else:
                            self.blocking_modal(
                                "Restore Filters",
                                "After checkout, return to your filtered results page.\n\n"
                                "When ready, click Continue."
                            )
                            list_url = driver.current_url
                    else:
                        self.blocking_modal("Cart Full", "Cart has 50 items. Checkout manually, then Continue.")
                        self.items_carted = 0

                # Add product to cart
                ok = self.add_product_to_cart(driver, wait, url, list_handle, list_url, add_wait, verify_t)
                if ok:
                    self.items_carted += 1
                    adds += 1

                # Cooldown to avoid rate limiting
                if cd_every > 0 and adds > 0 and adds % cd_every == 0:
                    self.log(f"COOLDOWN: sleeping {cd_s}s (anti-rate-limit)…")
                    time.sleep(cd_s)

                self.set_progress(int(((i) / max(1, len(urls2))) * 100))

            # Find Next page link
            nxt = self.find_next_page_el(driver)
            if not nxt:
                self.log("LIST: no Next page found — done scanning.")
                return

            # Navigate to next page CAREFULLY
            prev_url = driver.current_url
            self.log("LIST: navigating to next page…")
            
            try:
                # Try clicking the next link
                self.smart_click(driver, nxt)
            except Exception:
                # Fallback: try direct navigation
                try:
                    href = nxt.get_attribute("href")
                    if href:
                        driver.get(href)
                except Exception as e:
                    self.log(f"LIST: failed to navigate to next page: {e}")
                    return

            # Wait for page change
            time.sleep(page_wait)

            # Verify we moved to a new page
            for check in range(40):
                if self.stop_flag.is_set():
                    return
                try:
                    if driver.current_url != prev_url:
                        self.log(f"LIST: page changed successfully.")
                        break
                except Exception:
                    break
                time.sleep(0.3)
            else:
                self.log("WARN: URL did not change after clicking Next.")

    def add_product_to_cart(self, driver, wait, url, list_handle, list_url, add_wait, verify_t) -> bool:
        """
        Add a single product to cart.
        Opens product in NEW TAB to preserve list page filters.
        Returns True if successfully added.
        """
        before = None
        used_same_tab = False
        step = "start"

        try:
            # Pre-check for challenges
            if self.guard_interstitial(driver, "pre_add"):
                pass

            # Get current cart count
            try:
                before = self.get_cart_badge_count(driver)
                if before is not None:
                    self.log(f"ADD: cart before = {before}")
            except Exception:
                before = None

            # Open product in NEW TAB (preserves filters in list tab)
            step = "open_tab"
            try:
                driver.execute_script("window.open(arguments[0], '_blank');", url)
                time.sleep(0.5)
                handles = driver.window_handles
                driver.switch_to.window(handles[-1])
            except Exception as e:
                self.log(f"WARN: new tab failed ({e}), using same tab")
                used_same_tab = True
                driver.get(url)

            # Wait for product page to load
            step = "wait_body"
            try:
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            except Exception:
                pass
            time.sleep(1.5 + random.random() * 1.0)

            # Check for challenges on product page
            if self.guard_interstitial(driver, "product"):
                pass

            # Handle PWYW (Pay What You Want) - set to $0
            step = "pwyw"
            for fid in ["pwyw_price", "pwyw_amount", "amount", "price"]:
                try:
                    field = driver.find_element(By.ID, fid)
                    if field.is_displayed() and field.is_enabled():
                        try:
                            field.clear()
                            time.sleep(0.2)
                            field.send_keys("0")
                            time.sleep(0.2)
                            self.log("PWYW: set to $0")
                        except Exception:
                            pass
                        break
                except Exception:
                    continue

            # Find Add to Cart button
            step = "find_btn"
            btn = self.find_add_to_cart_button(driver)
            if not btn:
                self.log(f"⚠️ WARN: no Add-to-Cart button found: {url}")
                self.debug_dump(driver, "no_add_button")
                if self.pause_on_fail_var.get():
                    self.blocking_modal(
                        "Add-to-cart Button Missing",
                        f"Could not find Add-to-Cart button.\n\n{url}\n\n"
                        "Fix in Chrome (or skip this item), then Continue."
                    )
                return False

            # Click the button
            step = "click"
            method = self.smart_click(driver, btn)
            product_name = url.split('/')[-1][:50]
            self.log(f"ADD: clicked ({method}) → {product_name}")
            
            # Wait for add operation to complete
            time.sleep(add_wait)

            # Return to list tab
            step = "return_list"
            try:
                if not used_same_tab:
                    # Close product tab and return to list
                    driver.close()
                    driver.switch_to.window(list_handle)
                else:
                    # We used same tab - navigate back to list
                    if list_url:
                        driver.get(list_url)
                        time.sleep(2.0)
                    else:
                        driver.back()
                        time.sleep(2.0)
            except Exception as e:
                self.log(f"WARN: return to list failed: {e}")
                try:
                    driver.switch_to.window(list_handle)
                except Exception:
                    pass

            # Verify cart count increased
            step = "verify"
            if before is not None:
                ok = self.wait_cart_change(driver, before, timeout_s=verify_t)
                if ok is True:
                    self.log("✓ ADD: verified successful")
                    return True
                
                self.log("⚠️ WARN: cart count did not change (might be blocked or delayed)")
                if self.pause_on_fail_var.get():
                    self.debug_dump(driver, "cart_no_change")
                    self.blocking_modal(
                        "Cart Verification Failed",
                        f"Cart count did not change after clicking Add.\n\n"
                        f"Before: {before}\n"
                        f"Expected: {before + 1}\n\n"
                        "Check Chrome to see if item was added.\n"
                        "Then click Continue."
                    )
                return False

            # No cart count available - assume success
            return True

        except (WebDriverException, TimeoutException) as e:
            if is_invalid_session(e):
                raise
            self.log(f"⚠️ WARN: add failed at step={step}: {e}")
            self.debug_dump(driver, f"add_fail_{step}")
            return False

        except Exception as e:
            if is_invalid_session(e):
                raise
            self.log(f"⚠️ WARN: add failed at step={step}: {e}")
            self.debug_dump(driver, f"add_fail_{step}")
            return False

    # -----------------------------
    # Checkout -> Library -> Download
    # -----------------------------
    def checkout_and_download(self, driver, wait):
        if self.stop_flag.is_set():
            return

        self.log("CHECKOUT: opening cart…")
        driver.get("https://www.drivethrurpg.com/cart.php")
        time.sleep(3.0)

        if self.guard_interstitial(driver, "cart"):
            pass

        self.blocking_modal(
            "Checkout",
            "Complete the checkout in Chrome.\n\n"
            "IMPORTANT:\n"
            "• Verify total is $0.00 (or what you expect)\n"
            "• Complete checkout so items move to your Library\n\n"
            "When finished, click Continue."
        )

        if self.stop_flag.is_set():
            return

        self.log("LIBRARY: opening…")
        driver.get("https://www.drivethrurpg.com/en/library")
        time.sleep(4.0)

        if self.guard_interstitial(driver, "library_after_checkout"):
            pass

        # Click download links (best-effort)
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='download_file']")
        self.log(f"LIBRARY: found {len(links)} download links. Clicking first 50…")

        for i, a in enumerate(links[:50], start=1):
            if self.stop_flag.is_set():
                return
            try:
                self.smart_click(driver, a)
            except Exception:
                pass
            time.sleep(2.5)
            self.set_progress(int((i / max(1, min(50, len(links)))) * 100))


if __name__ == "__main__":
    root = tk.Tk()
    app = DTRPG_Enterprise_System(root)
    root.mainloop()

import os
import time
import shutil
import hashlib
import threading
import tkinter as tk
from tkinter import ttk, filedialog
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class DTRPG_Full_Auto_System:
    def __init__(self, root):
        self.root = root
        self.root.title("DriveThruRPG Full-Auto System")
        self.root.geometry("750x600")
        
        # Project Paths
        self.download_path = tk.StringVar(value=os.path.expanduser("~/Documents/DTRPG_QC_Project"))
        self.status_msg = tk.StringVar(value="Initializing System...")
        self.progress_val = tk.IntVar(value=0)
        
        # Categories for Organization
        self.CATEGORIES = {
            "Adventures": ["Adventure", "Module", "One-Shot", "Campaign", "Quest"],
            "Supplements": ["Supplement", "Guide", "Expansion", "Manual", "Rulebook"],
            "Maps": ["Map", "Battlemap", "Cartography", "Grid"],
            "Monsters": ["Monster", "Bestiary", "Creature", "Statblock"],
            "Characters": ["Character", "Class", "Subclass", "Race", "Background"]
        }
        
        self.setup_ui()

    def setup_ui(self):
        # Storage Config
        frame_dir = ttk.LabelFrame(self.root, text="Target Storage", padding=10)
        frame_dir.pack(fill="x", padx=10, pady=5)
        ttk.Entry(frame_dir, textvariable=self.download_path).pack(side="left", fill="x", expand=True)
        ttk.Button(frame_dir, text="Browse", command=lambda: self.download_path.set(filedialog.askdirectory())).pack(side="right")

        # Progress
        frame_prog = ttk.LabelFrame(self.root, text="Operational Status", padding=10)
        frame_prog.pack(fill="x", padx=10, pady=5)
        self.progress_bar = ttk.Progressbar(frame_prog, variable=self.progress_val, maximum=100)
        self.progress_bar.pack(fill="x", pady=5)
        ttk.Label(frame_prog, textvariable=self.status_msg).pack()

        # Log
        self.log_box = tk.Listbox(self.root, height=15, bg="#0a0a0a", fg="#00ff41", font=("Courier", 10))
        self.log_box.pack(fill="both", expand=True, padx=10, pady=5)

        self.start_btn = ttk.Button(self.root, text="EXECUTE ACQUISITION & ORGANIZE", command=self.start_thread)
        self.start_btn.pack(pady=10)

    def log(self, message):
        self.log_box.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}")
        self.log_box.see(tk.END)

    def find_chrome(self):
        """Automatically find the Chrome binary on Pop!_OS/Linux."""
        paths = ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium-browser']
        for path in paths:
            if os.path.exists(path):
                self.log(f"System: Chrome found at {path}")
                return path
        return None

    def get_file_hash(self, path):
        hasher = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def organize_and_dedupe(self):
        self.status_msg.set("Deduplicating & Organizing...")
        seen_hashes = {}
        base = self.download_path.get()
        
        # Catalog existing files to prevent duplicates
        for root, dirs, files in os.walk(base):
            for filename in files:
                f_path = os.path.join(root, filename)
                h = self.get_file_hash(f_path)
                if h in seen_hashes:
                    os.remove(f_path)
                    self.log(f"Dedupe: Removed duplicate {filename}")
                else:
                    seen_hashes[h] = f_path

        # Organize root files
        for filename in [f for f in os.listdir(base) if os.path.isfile(os.path.join(base, f))]:
            src = os.path.join(base, filename)
            moved = False
            for cat, keys in self.CATEGORIES.items():
                if any(k.lower() in filename.lower() for k in keys):
                    dest = os.path.join(base, cat)
                    os.makedirs(dest, exist_ok=True)
                    shutil.move(src, os.path.join(dest, filename))
                    moved = True
                    break
            if not moved:
                unsorted = os.path.join(base, "Unsorted")
                os.makedirs(unsorted, exist_ok=True)
                shutil.move(src, os.path.join(unsorted, filename))

    def start_thread(self):
        self.start_btn.config(state="disabled")
        threading.Thread(target=self.run_process, daemon=True).start()

    def run_process(self):
        chrome_path = self.find_chrome()
        if not chrome_path:
            self.log("ERROR: Chrome binary not found on system.")
            self.start_btn.config(state="normal")
            return

        options = uc.ChromeOptions()
        options.add_experimental_option("prefs", {
            "download.default_directory": self.download_path.get(),
            "plugins.always_open_pdf_externally": True
        })

        try:
            driver = uc.Chrome(options=options, browser_executable_path=chrome_path, version_main=144)
            wait = WebDriverWait(driver, 20)

            # Step 1: Login
            driver.get("https://www.drivethrurpg.com/login.php")
            self.status_msg.set("Waiting for Manual Login...")
            while "login" in driver.current_url: time.sleep(2)

            # Step 2: Acquire
            self.status_msg.set("Scanning D&D PWYW...")
            driver.get("https://www.drivethrurpg.com/en/browse?pwvw=true&ruleSystem=44827")
            time.sleep(5)
            
            links = [l.get_attribute('href') for l in driver.find_elements(By.CSS_SELECTOR, "a.product-title")]
            for i, url in enumerate(links):
                try:
                    driver.get(url)
                    p_field = wait.until(EC.presence_of_element_located((By.ID, "pwyw_price")))
                    p_field.clear()
                    p_field.send_keys("0")
                    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='submit'][value*='Cart']"))).click()
                    self.log(f"Acquired: {url.split('/')[-1]}")
                except: self.log(f"Skipped: {url.split('/')[-1]}")
                self.progress_val.set(int(((i+1)/len(links))*100))
                time.sleep(5)

            # Step 3: Checkout
            driver.get("https://www.drivethrurpg.com/shopping_cart.php")
            try:
                wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Checkout"))).click()
                wait.until(EC.element_to_be_clickable((By.ID, "confirm_button"))).click()
                self.log("Checkout Complete.")
            except: self.log("Cart already empty.")

            # Step 4: Organize
            self.organize_and_dedupe()
            self.log("All content organized and duplicates cleared.")

        except Exception as e: self.log(f"Critical Error: {str(e)}")
        finally:
            self.status_msg.set("Process Complete")
            self.start_btn.config(state="normal")

if __name__ == "__main__":
    root = tk.Tk()
    app = DTRPG_Full_Auto_System(root)
    root.mainloop()

#!/usr/bin/env python3
"""
DTRPG Free PDF Grabber v2
- Works directly on the filtered browse page
- Clicks cart icons on product cards (no page navigation needed)
- Handles pagination
- Checkouts at 50 items, then resumes
- Skips already-owned items
"""

import os
import time
import shutil
import threading
from pathlib import Path
from queue import Queue, Empty

import tkinter as tk
from tkinter import ttk, filedialog

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, 
    StaleElementReferenceException, ElementClickInterceptedException
)

# Configuration
USER_HOME = Path.home()
AUTO_PROFILE_PATH = USER_HOME / ".config/google-chrome-dtrpg-automation"
DEFAULT_STORAGE = USER_HOME / "Documents/DTRPG_Downloads"
CART_LIMIT = 50


def which_chrome() -> str:
    """Find Chrome binary."""
    for p in ["/usr/bin/google-chrome-stable", "/usr/bin/google-chrome", 
              "/usr/bin/chromium-browser", "/usr/bin/chromium"]:
        if Path(p).exists():
            return p
    for name in ["google-chrome-stable", "google-chrome", "chromium-browser", "chromium"]:
        p = shutil.which(name)
        if p:
            return p
    return "/usr/bin/google-chrome"


CHROME_BIN = which_chrome()


class DTRPGFreeGrabber:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("DTRPG Free PDF Grabber v3")
        self.root.geometry("800x600")
        
        self.download_path = tk.StringVar(value=str(DEFAULT_STORAGE))
        self.status_msg = tk.StringVar(value="Ready")
        self.progress_val = tk.IntVar(value=0)
        
        self.keep_chrome_var = tk.BooleanVar(value=True)
        
        self.driver = None
        self.items_added = 0
        self.items_skipped = 0
        self.owned_products = set()  # Track product IDs we already own
        self.already_in_cart = set()  # Track what we've added this session
        self.skipped_for_retry = []  # Items that failed but might work on retry
        
        self.uiq: Queue = Queue()
        self.running = False
        
        self.setup_ui()
        self.root.after(80, self._drain_ui_queue)
    
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
        self.root.after(80, self._drain_ui_queue)
    
    def ui(self, fn):
        self.uiq.put(fn)
    
    def log(self, message: str):
        ts = time.strftime("%H:%M:%S")
        def _do():
            self.log_box.insert(tk.END, f"[{ts}] {message}\n")
            self.log_box.see(tk.END)
        self.ui(_do)
    
    def set_status(self, s: str):
        self.ui(lambda: self.status_msg.set(s))
    
    def set_progress(self, pct: int):
        self.ui(lambda: self.progress_val.set(max(0, min(100, int(pct)))))
    
    def setup_ui(self):
        # Instructions
        inst_frame = ttk.LabelFrame(self.root, text="Instructions", padding=10)
        inst_frame.pack(fill="x", padx=10, pady=5)
        
        instructions = """1. Click 'Start Chrome' to open browser
2. Log in to DriveThruRPG  
3. Navigate to your filtered page (e.g., Free D&D PDFs)
4. Click 'Grab Free PDFs' to start collecting
5. At 50 items, you'll be prompted to checkout"""
        
        ttk.Label(inst_frame, text=instructions, justify="left").pack(anchor="w")
        
        # Options
        opt_frame = ttk.LabelFrame(self.root, text="Options", padding=10)
        opt_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Checkbutton(opt_frame, text="Keep Chrome open after completion",
                        variable=self.keep_chrome_var).pack(side="left", padx=10)
        
        # Storage path
        dir_frame = ttk.LabelFrame(self.root, text="Download Folder", padding=10)
        dir_frame.pack(fill="x", padx=10, pady=5)
        ttk.Entry(dir_frame, textvariable=self.download_path).pack(side="left", fill="x", expand=True)
        ttk.Button(dir_frame, text="Browse", command=self._browse_dir).pack(side="right")
        
        # Progress
        prog_frame = ttk.LabelFrame(self.root, text="Progress", padding=10)
        prog_frame.pack(fill="x", padx=10, pady=5)
        ttk.Progressbar(prog_frame, variable=self.progress_val, maximum=100).pack(fill="x", pady=5)
        ttk.Label(prog_frame, textvariable=self.status_msg).pack()
        
        # Log
        log_frame = ttk.Frame(self.root)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.log_box = tk.Text(log_frame, height=12, bg="#1a1a1a", fg="#00ff00", 
                               font=("Courier", 10), wrap="word")
        yscroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=yscroll.set)
        self.log_box.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        
        # Buttons
        btn_frame = ttk.Frame(self.root, padding=8)
        btn_frame.pack(fill="x")
        
        self.chrome_btn = ttk.Button(btn_frame, text="1. Start Chrome", command=self.start_chrome)
        self.chrome_btn.pack(side="left", padx=5)
        
        self.grab_btn = ttk.Button(btn_frame, text="2. Grab Free PDFs", command=self.start_grabbing, state="disabled")
        self.grab_btn.pack(side="left", padx=5)
        
        self.stop_btn = ttk.Button(btn_frame, text="Stop", command=self.stop_grabbing, state="disabled")
        self.stop_btn.pack(side="left", padx=5)
        
        ttk.Button(btn_frame, text="Quit", command=self.quit_app).pack(side="right", padx=5)
    
    def _browse_dir(self):
        d = filedialog.askdirectory()
        if d:
            self.download_path.set(d)
    
    def blocking_modal(self, title: str, msg: str, button_text="Continue"):
        """Show a blocking modal dialog."""
        gate = threading.Event()
        
        def _do():
            win = tk.Toplevel(self.root)
            win.title(title)
            win.transient(self.root)
            win.grab_set()
            win.attributes("-topmost", True)
            
            frm = ttk.Frame(win, padding=20)
            frm.pack(fill="both", expand=True)
            
            ttk.Label(frm, text=msg, justify="left", wraplength=400).pack(pady=10)
            
            def close():
                win.grab_release()
                win.destroy()
                gate.set()
            
            ttk.Button(frm, text=button_text, command=close).pack(pady=10)
            win.protocol("WM_DELETE_WINDOW", close)
            
            # Center on parent
            win.update_idletasks()
            x = self.root.winfo_rootx() + (self.root.winfo_width() // 2) - (win.winfo_width() // 2)
            y = self.root.winfo_rooty() + (self.root.winfo_height() // 2) - (win.winfo_height() // 2)
            win.geometry(f"+{max(0, x)}+{max(0, y)}")
        
        self.ui(_do)
        gate.wait()
    
    def start_chrome(self):
        """Start Chrome browser."""
        self.chrome_btn.config(state="disabled")
        threading.Thread(target=self._start_chrome_thread, daemon=True).start()
    
    def _start_chrome_thread(self):
        try:
            self.log("Starting Chrome...")
            AUTO_PROFILE_PATH.mkdir(parents=True, exist_ok=True)
            
            # Clean up locks
            for ln in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
                p = AUTO_PROFILE_PATH / ln
                try:
                    if p.exists():
                        p.unlink()
                except:
                    pass
            
            options = uc.ChromeOptions()
            options.add_argument("--disable-popup-blocking")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--no-first-run")
            options.add_argument("--no-sandbox")
            options.add_argument(f"--user-data-dir={str(AUTO_PROFILE_PATH)}")
            
            prefs = {
                "download.default_directory": self.download_path.get(),
                "download.prompt_for_download": False,
                "plugins.always_open_pdf_externally": True,
            }
            options.add_experimental_option("prefs", prefs)
            
            self.driver = uc.Chrome(
                options=options,
                browser_executable_path=CHROME_BIN,
                use_subprocess=True,
                version_main=144
            )
            
            self.driver.get("https://www.drivethrurpg.com/en/")
            self.log("✓ Chrome started!")
            self.log("Log in and navigate to your filtered page, then click 'Grab Free PDFs'")
            self.set_status("Chrome ready - navigate to your filtered page")
            
            self.ui(lambda: self.grab_btn.config(state="normal"))
            
        except Exception as e:
            self.log(f"✗ Failed to start Chrome: {e}")
            self.ui(lambda: self.chrome_btn.config(state="normal"))
    
    def start_grabbing(self):
        """Start the grabbing process."""
        self.grab_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.running = True
        self.items_added = 0
        self.items_skipped = 0
        threading.Thread(target=self._grab_thread, daemon=True).start()
    
    def stop_grabbing(self):
        """Stop the grabbing process."""
        self.running = False
        self.log("Stopping...")
    
    def _grab_thread(self):
        """Main grabbing logic."""
        try:
            self.set_status("Scanning page for free products...")
            
            page_num = 1
            total_pages = self._get_total_pages()
            self.skipped_for_retry = []  # Items that failed but might work on retry
            self.already_in_cart = set()  # Track what we've added
            
            while self.running:
                self.log(f"=== Page {page_num} of {total_pages} ===")
                
                # Process current page
                added_on_page, skipped_on_page = self._process_current_page()
                
                self.log(f"Page {page_num}: Added {added_on_page}, Skipped {skipped_on_page} (Cart: {self.items_added})")
                
                # Check if we need to checkout
                if self.items_added >= CART_LIMIT:
                    self._do_checkout()
                    if not self.running:
                        break
                
                # Try to go to next page
                if not self._go_to_next_page():
                    self.log("No more pages!")
                    break
                
                page_num += 1
            
            # Retry skipped items
            if self.running and self.skipped_for_retry:
                self.log(f"=== RETRYING {len(self.skipped_for_retry)} SKIPPED ITEMS ===")
                retry_count = self._retry_skipped_items()
                self.log(f"Retry added {retry_count} more items")
            
            # Final checkout if we have items
            if self.items_added > 0:
                self._do_checkout()
            
            self.log(f"=== DONE === Added: {self.items_added}, Skipped: {self.items_skipped}")
            self.set_status("Complete!")
            
        except Exception as e:
            self.log(f"ERROR: {e}")
            import traceback
            self.log(traceback.format_exc())
            self.set_status("Error!")
        finally:
            self.running = False
            self.ui(lambda: self.grab_btn.config(state="normal"))
            self.ui(lambda: self.stop_btn.config(state="disabled"))
            
            if not self.keep_chrome_var.get() and self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
    
    def _get_total_pages(self) -> int:
        """Try to get total page count from pagination."""
        try:
            # Look for pagination numbers
            pages = self.driver.find_elements(By.CSS_SELECTOR, "ul.pagination li a, .pagination a")
            if pages:
                nums = []
                for p in pages:
                    txt = p.text.strip()
                    if txt.isdigit():
                        nums.append(int(txt))
                if nums:
                    return max(nums)
        except:
            pass
        return 99  # Unknown
    
    def _process_current_page(self) -> tuple:
        """Process all products on current page. Returns (added, skipped) counts."""
        added = 0
        skipped = 0
        
        try:
            # Wait for products to load - look for obs-card-result elements
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "obs-card-result"))
            )
            # IMPORTANT: Wait 5 seconds for Angular to fully render all cards
            time.sleep(5)
            
            # Find all product cards
            cards = self.driver.find_elements(By.CSS_SELECTOR, "obs-card-result")
            self.log(f"Found {len(cards)} product cards on this page")
            
            if len(cards) == 0:
                self.log("WARNING: No cards found - page may not have loaded properly")
                time.sleep(3)
                cards = self.driver.find_elements(By.CSS_SELECTOR, "obs-card-result")
                self.log(f"Retry found {len(cards)} cards")
            
            for i, card in enumerate(cards):
                if not self.running:
                    break
                if self.items_added >= CART_LIMIT:
                    self.log(f"Reached cart limit ({CART_LIMIT}), need to checkout")
                    break
                
                try:
                    # Get product ID/URL for deduplication
                    product_links = card.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
                    product_url = product_links[0].get_attribute("href") if product_links else None
                    
                    # Extract product ID from URL
                    product_id = None
                    if product_url:
                        import re
                        match = re.search(r'/product/(\d+)/', product_url)
                        if match:
                            product_id = match.group(1)
                    
                    # Skip if already in our cart this session
                    if product_id and product_id in self.already_in_cart:
                        continue
                    
                    # Check if already owned - look for ".product-banner.bought"
                    owned_banners = card.find_elements(By.CSS_SELECTOR, ".product-banner.bought")
                    if owned_banners:
                        self.items_skipped += 1
                        skipped += 1
                        continue  # Skip owned items silently
                    
                    # Check price - must be $0.00
                    price_els = card.find_elements(By.CSS_SELECTOR, "obs-price .cy-prc")
                    if not price_els:
                        continue
                    
                    price_text = price_els[0].text.strip()
                    if price_text != "$0.00":
                        continue  # Not free
                    
                    # Get product name for logging
                    name_els = card.find_elements(By.CSS_SELECTOR, "h5")
                    product_name = name_els[0].text if name_els else f"Product #{i}"
                    
                    # Find the add-to-cart button
                    cart_btns = card.find_elements(By.CSS_SELECTOR, "button.atc-btn.btn-purchase")
                    if not cart_btns:
                        # Fallback selector
                        cart_btns = card.find_elements(By.CSS_SELECTOR, "obs-add-to-cart-button button")
                    
                    if not cart_btns:
                        self.log(f"No cart button found for: {product_name[:30]}")
                        # Save for retry
                        if product_url:
                            self.skipped_for_retry.append({
                                'url': product_url,
                                'name': product_name,
                                'id': product_id,
                                'reason': 'no_button'
                            })
                        skipped += 1
                        continue
                    
                    btn = cart_btns[0]
                    
                    # Click it
                    if self._click_cart_button(btn, product_name):
                        added += 1
                        self.items_added += 1
                        if product_id:
                            self.already_in_cart.add(product_id)
                        self.log(f"[{self.items_added}] Added: {product_name[:50]}")
                    else:
                        # Failed to add - save for retry if not owned
                        skipped += 1
                        if product_url and product_id:
                            self.skipped_for_retry.append({
                                'url': product_url,
                                'name': product_name,
                                'id': product_id,
                                'reason': 'click_failed'
                            })
                    
                except StaleElementReferenceException:
                    # Page may have updated, skip this card
                    skipped += 1
                    continue
                except Exception as e:
                    self.log(f"Card error: {e}")
                    skipped += 1
            
        except TimeoutException:
            self.log("Timeout waiting for products to load - trying to continue")
        except Exception as e:
            self.log(f"Page processing error: {e}")
        
        return (added, skipped)
    
    def _click_cart_button(self, btn, product_name: str = "") -> bool:
        """Click a cart button. Returns True if successful."""
        try:
            # Scroll into view
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
            time.sleep(0.4)
            
            # Get cart count before
            before = self._get_cart_count()
            
            # Try regular click first
            try:
                btn.click()
            except ElementClickInterceptedException:
                # Use JS click if regular click is blocked
                self.driver.execute_script("arguments[0].click();", btn)
            
            # Wait for cart update
            time.sleep(1.2)
            
            # Check if cart count increased
            after = self._get_cart_count()
            
            if after > before:
                return True
            else:
                # Sometimes the button animation takes longer, check again
                time.sleep(0.5)
                after2 = self._get_cart_count()
                if after2 > before:
                    return True
                # Didn't add - might already be owned or in cart
                return False
                
        except Exception as e:
            self.log(f"Click failed for {product_name[:30]}: {e}")
            return False
    
    def _get_cart_count(self) -> int:
        """Get current cart item count."""
        try:
            # Try various selectors for cart count
            for sel in ["[data-cy='cartCount']", ".cart-item-count", "#cart_count", 
                        ".cart-count", "[class*='cart'] [class*='count']"]:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    txt = el.text.strip()
                    digits = ''.join(c for c in txt if c.isdigit())
                    if digits:
                        return int(digits)
                except:
                    pass
        except:
            pass
        return 0
    
    def _go_to_next_page(self) -> bool:
        """Click next page button. Returns True if successful."""
        try:
            # The Next button uses: a[aria-label="Next"]
            # Parent li will have class "disabled" if on last page
            
            next_links = self.driver.find_elements(By.CSS_SELECTOR, 'a[aria-label="Next"]')
            
            for link in next_links:
                try:
                    # Check if parent li has "disabled" class
                    parent_li = link.find_element(By.XPATH, "..")
                    parent_classes = parent_li.get_attribute("class") or ""
                    
                    if "disabled" in parent_classes:
                        self.log("On last page - no more pages")
                        return False
                    
                    if link.is_displayed():
                        self.log("Clicking next page...")
                        # Scroll to it and click
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link)
                        time.sleep(0.5)
                        link.click()
                        
                        # IMPORTANT: Wait 5 seconds for page to fully load
                        self.log("Waiting for page to load (5 seconds)...")
                        time.sleep(5)
                        
                        # Verify page changed by waiting for products
                        WebDriverWait(self.driver, 15).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "obs-card-result"))
                        )
                        return True
                        
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    self.log(f"Next button error: {e}")
            
            # Fallback: URL-based pagination
            self.log("Using URL-based pagination fallback...")
            current_url = self.driver.current_url
            if "page=" in current_url:
                import re
                match = re.search(r'page=(\d+)', current_url)
                if match:
                    current_page = int(match.group(1))
                    new_url = current_url.replace(f"page={current_page}", f"page={current_page + 1}")
                    self.driver.get(new_url)
                    self.log("Waiting for page to load (5 seconds)...")
                    time.sleep(5)
                    return True
            else:
                # Add page=2 if not present and we're on page 1
                if "?" in current_url:
                    new_url = current_url + "&page=2"
                else:
                    new_url = current_url + "?page=2"
                self.driver.get(new_url)
                self.log("Waiting for page to load (5 seconds)...")
                time.sleep(5)
                return True
            
        except Exception as e:
            self.log(f"Pagination error: {e}")
        
        return False
    
    def _retry_skipped_items(self) -> int:
        """Retry items that were skipped due to errors (not owned items)."""
        retry_added = 0
        
        # Filter out duplicates and items already in cart
        items_to_retry = []
        seen_ids = set()
        for item in self.skipped_for_retry:
            if item['id'] and item['id'] not in self.already_in_cart and item['id'] not in seen_ids:
                items_to_retry.append(item)
                seen_ids.add(item['id'])
        
        self.log(f"Retrying {len(items_to_retry)} unique items...")
        
        for item in items_to_retry:
            if not self.running:
                break
            if self.items_added >= CART_LIMIT:
                break
            
            try:
                self.log(f"Retry: {item['name'][:40]}...")
                
                # Navigate to product page
                self.driver.get(item['url'])
                time.sleep(3)
                
                # Look for add to cart button on product page
                cart_btns = self.driver.find_elements(By.CSS_SELECTOR, 
                    "button.atc-btn.btn-purchase, "
                    "button[aria-label*='Add to Cart'], "
                    ".add-to-cart-btn, "
                    "[data-cy*='addToCart'] button"
                )
                
                if cart_btns:
                    before = self._get_cart_count()
                    cart_btns[0].click()
                    time.sleep(2)
                    after = self._get_cart_count()
                    
                    if after > before:
                        retry_added += 1
                        self.items_added += 1
                        self.already_in_cart.add(item['id'])
                        self.log(f"  ✓ Added on retry!")
                    else:
                        self.log(f"  ✗ Still couldn't add")
                else:
                    self.log(f"  ✗ No cart button found on product page")
                    
            except Exception as e:
                self.log(f"  ✗ Retry error: {e}")
        
        return retry_added
    
    def _do_checkout(self):
        """Handle checkout process."""
        self.log(f"=== CHECKOUT ({self.items_added} items) ===")
        self.set_status("Time to checkout!")
        
        # Navigate to cart
        self.driver.get("https://www.drivethrurpg.com/en/cart")
        time.sleep(3)
        
        self.blocking_modal(
            "Checkout Time!",
            f"You have {self.items_added} items in your cart.\n\n"
            "1. Verify total is $0.00\n"
            "2. Complete checkout in the browser\n"
            "3. Click Continue when done\n\n"
            "(Or close this to stop)",
            "Continue"
        )
        
        # Ask about auto-download
        self.blocking_modal(
            "Download Files?",
            "Would you like to auto-download the files from your library?\n\n"
            "Click 'Auto Download' to download newly added items,\n"
            "or 'Skip' to continue grabbing without downloading.",
            "Auto Download"
        )
        
        # Try to auto-download from library
        self._auto_download_from_library()
        
        # Reset counter
        self.items_added = 0
        
        # Go back to browse page - user needs to navigate back
        self.blocking_modal(
            "Navigate Back",
            "Please navigate back to your filtered page in the browser,\n"
            "then click Continue.",
            "Continue"
        )
    
    def _auto_download_from_library(self):
        """Go to library and download recent items."""
        try:
            self.log("=== AUTO-DOWNLOADING FROM LIBRARY ===")
            self.driver.get("https://www.drivethrurpg.com/en/mylibrary")
            time.sleep(5)
            
            # Wait for library to load
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "obs-file-list, .library-item, [data-cy*='library']"))
            )
            time.sleep(2)
            
            # Look for download buttons - these may vary
            # Common patterns: "Download" links, download icons, etc.
            download_btns = self.driver.find_elements(By.CSS_SELECTOR,
                "a[href*='download'], "
                "button[aria-label*='Download'], "
                "a[aria-label*='Download'], "
                ".download-btn, "
                "[data-cy*='download']"
            )
            
            self.log(f"Found {len(download_btns)} download buttons")
            
            # Click first 50 download buttons (the ones we just added)
            downloaded = 0
            for btn in download_btns[:50]:
                if not self.running:
                    break
                try:
                    if btn.is_displayed():
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        time.sleep(0.3)
                        btn.click()
                        downloaded += 1
                        time.sleep(1)  # Brief pause between downloads
                except:
                    pass
            
            self.log(f"Triggered {downloaded} downloads")
            
            # Wait for downloads to start
            if downloaded > 0:
                self.log("Waiting for downloads to start...")
                time.sleep(5)
                
        except Exception as e:
            self.log(f"Auto-download error: {e}")
            self.log("You can manually download from your library")
    
    def quit_app(self):
        """Clean up and quit."""
        self.running = False
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = DTRPGFreeGrabber(root)
    root.mainloop()

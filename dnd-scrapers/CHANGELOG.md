# DTRPG Scraper - Complete Code Review & Fixes

## Critical Issues Fixed

### 1. **Auto-Login Strengthened** ✅
**Problem:** Auto-login wasn't working reliably
**Fixes:**
- Added explicit 2-second wait after loading login page
- Added check for already-logged-in state before attempting login
- Increased field interaction delays (0.2-0.3s between actions)
- Extended login confirmation wait from 10s to 15s (60 iterations @ 0.25s)
- Added explicit URL check to ensure we're NOT on login page after success
- Better logging at each step for debugging

### 2. **False Positive Verification Detection** ✅
**Problem:** System kept claiming verification pages appeared when they didn't
**Fixes:**
- Made `guard_interstitial()` MUCH more strict
- Only triggers on REAL Cloudflare challenge elements:
  - `cf-browser-verification` (actual challenge div)
  - `challenge-platform` (Cloudflare challenge)
  - `cdn-cgi/challenge` (challenge URL path)
- Title matching now uses EXACT match, not substring:
  - "just a moment..." (exact)
  - NOT "a page about moments" (would have triggered before)
- Removed generic keywords that appear in normal content
- Added better logging when real challenges are detected

### 3. **Timing & Stability Improvements** ✅
**Problem:** Moving too fast, losing filters, crashing
**Fixes:**
- Increased default timings:
  - `add_wait_s`: 3.0 → 4.0 seconds
  - `page_wait_s`: 6.0 → 7.0 seconds
  - `verify_timeout_s`: 22.0 → 25.0 seconds
- Added randomized delays to mimic human behavior:
  - Page scanning: 1.2s + random 0.8s
  - Product load: 1.5s + random 1.0s
- Increased tab switch delay: 0.35s → 0.5s
- Added 0.2s delays between form field interactions
- Increased scroll-before-click: 0.25s → 0.3s

### 4. **Filter Preservation Enhanced** ✅
**Problem:** Filters getting lost, requiring manual restore
**Fixes:**
- Added `seed_list_url` to store original filtered URL
- Better detection of lost filters (checks for product links)
- Improved navigation back to list page:
  - After product: closes tab and returns to list handle
  - After cart full: automatically returns to seed URL
- Changed from `driver.back()` to keeping list tab open throughout
- More explicit list state management (handle + URL tracking)
- Added verification that URL changed after pagination

### 5. **Code Quality & Safety** ✅
**Fixes:**
- Removed all malformed patch code that caused IndentationError
- Cleaned up indentation throughout
- Fixed `is_logged_in()` to also check URL (not just HTML content)
- Improved `find_next_page_el()` to verify pagination links
- Better error messages with emoji indicators (⚠️, ✓)
- Changed log_box from Listbox to Text widget for better word wrapping
- Added verification that Next links contain page params

### 6. **Better Error Handling** ✅
- Added product name truncation in logs (first 50 chars)
- More detailed step tracking in add_product_to_cart
- Debug dumps include step name for easier troubleshooting
- Better exception messages showing which step failed
- Improved modal dialogs with clearer instructions

### 7. **Cart Verification Improved** ✅
- `wait_cart_change()` now logs the actual cart transition
- Increased polling interval: 0.35s → 0.4s
- Better timeout messaging showing expected vs actual counts
- Added logging of cart count before each add attempt

## Usage Instructions

### Deploy the fixed version:
```bash
cd ~/dev/dnd-scrapers
cp dtrpg_qc_fixed.py dtrpg_qc.py
```

### Set environment variables (if using auto-login):
```bash
export DTRPG_EMAIL="your@email.com"
export DTRPG_PASSWORD="yourpassword"
```

### Run:
```bash
source venv/bin/activate
python3 dtrpg_qc.py
```

## Key Behavioral Changes

### Auto-Login Flow:
1. Loads login page
2. Waits 2 seconds for full load
3. Checks if already logged in (skip if yes)
4. Fills email field → wait 0.2s
5. Types email → wait 0.3s
6. Fills password field → wait 0.2s
7. Types password → wait 0.3s
8. Clicks submit (or tries form submit)
9. Polls for 15 seconds checking login status
10. Verifies NOT on /login URL
11. Success or timeout

### Verification Detection:
- **Will NOT trigger on**: Normal product descriptions mentioning "moment", "verify", "browser"
- **Will ONLY trigger on**: Actual Cloudflare challenge pages with specific technical elements

### Filter Preservation:
1. User sets filters and confirms on results page
2. System locks `seed_list_url` = current filtered results URL
3. For each product:
   - Opens in NEW tab
   - Adds to cart
   - Closes tab, returns to list handle
4. After 50 items (cart full):
   - Auto-navigates back to `seed_list_url`
   - Filters remain intact

## Testing Checklist

- [ ] Auto-login works with env vars set
- [ ] No false verification warnings on normal pages
- [ ] Filters stay intact through multiple pages
- [ ] Cart count verification works
- [ ] System doesn't crash after adding items
- [ ] Proper waiting between operations (no rushing)
- [ ] Debug dumps created in `_debug/` folder when issues occur
- [ ] Modal dialogs appear on top and are visible

## Debug Features

All debug dumps go to: `<download_folder>/_debug/`

Each dump includes:
- Screenshot (PNG)
- Full HTML source
- Current URL

Debug dump triggers:
- Verification detected
- No products found
- No Add-to-cart button
- Cart verification failed
- Any critical exception

## Environment Variable Overrides

You can override timing via env vars:
```bash
DTRPG_ADD_WAIT=5.0 \
DTRPG_PAGE_WAIT=8.0 \
DTRPG_VERIFY_TIMEOUT=30 \
DTRPG_COOLDOWN_EVERY=3 \
DTRPG_COOLDOWN_S=12 \
python3 dtrpg_qc.py
```

## Notes

- Text-based log box for better readability
- Increased waits make it more human-like
- Stricter verification detection = fewer interruptions
- Filter preservation = no more manual restore
- Auto-login should "just work" now

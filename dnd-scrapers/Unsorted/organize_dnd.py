import os
import shutil
import hashlib

BASE_DIR = os.path.expanduser("~/Documents/DTRPG_QC_Project")
CATEGORIES = {
    "Adventures": ["Adventure", "Module", "One-Shot", "Campaign", "Quest"],
    "Supplements": ["Supplement", "Guide", "Expansion", "Manual", "Rulebook"],
    "Maps": ["Map", "Battlemap", "Cartography", "Grid"],
    "Monsters": ["Monster", "Bestiary", "Creature", "Statblock"],
    "Characters": ["Character", "Class", "Subclass", "Race", "Background"]
}

def get_file_hash(path):
    """Calculate MD5 hash to identify identical content regardless of filename."""
    hasher = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def organize_and_dedupe():
    seen_hashes = {}
    
    # 1. First, scan existing categorized folders to catalog what we already have
    for root, dirs, files in os.walk(BASE_DIR):
        for filename in files:
            file_path = os.path.join(root, filename)
            f_hash = get_file_hash(file_path)
            
            if f_hash in seen_hashes:
                print(f"[DUPE REMOVED] Already have content of {filename} at {seen_hashes[f_hash]}")
                os.remove(file_path)
            else:
                seen_hashes[f_hash] = file_path

    # 2. Organize new files in the root BASE_DIR
    new_files = [f for f in os.listdir(BASE_DIR) if os.path.isfile(os.path.join(BASE_DIR, f))]
    
    for filename in new_files:
        src = os.path.join(BASE_DIR, filename)
        f_hash = get_file_hash(src)
        
        # Final check if the new download is a duplicate of something already sorted
        if f_hash in seen_hashes:
            print(f"[DUPE REMOVED] New download {filename} is a duplicate. Deleting.")
            os.remove(src)
            continue

        moved = False
        lower_name = filename.lower()
        for category, keywords in CATEGORIES.items():
            if any(key.lower() in lower_name for key in keywords):
                dest_dir = os.path.join(BASE_DIR, category)
                os.makedirs(dest_dir, exist_ok=True)
                shutil.move(src, os.path.join(dest_dir, filename))
                print(f"Moved {filename} -> {category}")
                seen_hashes[f_hash] = os.path.join(dest_dir, filename)
                moved = True
                break
        
        if not moved:
            unsorted_dir = os.path.join(BASE_DIR, "Unsorted")
            os.makedirs(unsorted_dir, exist_ok=True)
            shutil.move(src, os.path.join(unsorted_dir, filename))

if __name__ == "__main__":
    organize_and_dedupe()

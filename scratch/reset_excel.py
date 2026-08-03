import pandas as pd
import shutil
from pathlib import Path

def main():
    original_path = Path("config/devices.xlsx")
    backup_path = Path("config/devices_backup.xlsx")
    
    if not original_path.exists():
        print(f"Error: Original Excel file not found at {original_path}")
        return
        
    # Create backup if it doesn't exist yet
    if not backup_path.exists():
        print(f"Creating backup: {backup_path}...")
        shutil.copy(original_path, backup_path)
        
    # Read sheet, slice to first row only
    df = pd.read_excel(original_path)
    df_single = df.iloc[[0]]
    
    # Save back
    df_single.to_excel(original_path, index=False)
    print("Successfully updated config/devices.xlsx to contain only 1 active device.")
    print("Backup of the original layout preserved at config/devices_backup.xlsx")

if __name__ == "__main__":
    main()

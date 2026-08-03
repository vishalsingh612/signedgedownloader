import pandas as pd
from pathlib import Path

def main():
    excel_path = Path("config/devices.xlsx")
    if not excel_path.exists():
        print(f"Error: Excel file not found at {excel_path}")
        return
        
    print(f"Reading excel file: {excel_path}...")
    df = pd.read_excel(excel_path)
    
    print("Current devices in sheet:")
    print(df)
    
    # Update the first device name to B0077-chittorgarh-Midland Microfin Ltd,
    target_device = "B0077-chittorgarh-Midland Microfin Ltd,"
    df.loc[0, "Device Name"] = target_device
    print(f"\nUpdating first row device name to: '{target_device}'")
    
    # Save back
    df.to_excel(excel_path, index=False)
    print("Excel file successfully updated!")

if __name__ == "__main__":
    main()

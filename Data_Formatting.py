import pandas as pd
import json
import numpy as np

def create_data_json(file_path, output_path='data.json'):
    """
    Reads trainer data from an Excel file, processes it, and saves it as a clean JSON file
    for the web dashboard.

    Args:
        file_path (str): The path to the DFLT_Mapping.xlsx file.
        output_path (str): The path where the output data.json file will be saved.
    """
    try:
        # Load the specified sheet from the Excel file
        df = pd.read_excel(file_path, sheet_name='ASPCs_Punjab')
        print("✅ Successfully loaded the Excel file.")
    except FileNotFoundError:
        print(f"❌ Error: The file was not found at {file_path}")
        return
    except Exception as e:
        print(f"❌ An error occurred while reading the Excel file: {e}")
        return

    # --- 1. Filter for 'Under Consideration' and clean data ---
    df.rename(columns={'Under Consideration?': 'Under_Consideration'}, inplace=True)
    # Convert to numeric, coercing errors to NaN, then fill NaN with 0
    df['Under_Consideration'] = pd.to_numeric(df['Under_Consideration'], errors='coerce').fillna(0)
    considered_df = df[df['Under_Consideration'] == 1].copy()
    print(f"➡️ Found {len(considered_df)} trainers marked for consideration.")

    # --- 2. Process data into a structured dictionary ---
    districts_data = {}

    for _, record in considered_df.iterrows():
        district_name = record.get('DISTRICT', 'Unknown').strip()
        tehsil_name = record.get('DUTY STATION(TEHSIL)', 'Unknown').strip()
        lat = record.get('Latitude')
        lon = record.get('Longitude')

        # Validate essential data
        if not all([district_name, tehsil_name, pd.notna(lat), pd.notna(lon)]):
            print(f"⚠️ Skipping record for {record.get('NAME')} due to missing data.")
            continue

        # Initialize district
        if district_name not in districts_data:
            districts_data[district_name] = {
                "name": district_name,
                "tehsils": {},
                "totalTrainers": 0,
                "totalHeadCount": 0,
                "ruralCount": 0,
                "urbanCount": 0
            }

        # Initialize tehsil
        if tehsil_name not in districts_data[district_name]["tehsils"]:
            districts_data[district_name]["tehsils"][tehsil_name] = {
                "name": tehsil_name,
                "district": district_name,
                "coords": [float(lat), float(lon)],
                "trainers": [],
                "isPair": False,
                "pairStatus": "NONE"
            }

        # Add trainer
        trainer = {
            "name": record.get('NAME'),
            "cnic": str(record.get('CNIC')),
            "headCount": int(record.get('Total Head Count', 0)),
            "isTopPerformer": record.get('Top_Performer?') == 'Top_Performer',
            "ruralUrban": record.get('Rural/Urban')
        }
        districts_data[district_name]["tehsils"][tehsil_name]["trainers"].append(trainer)

    # --- 3. Perform secondary calculations (pairing, stats) ---
    for district in districts_data.values():
        tehsil_head_counts = set()
        for tehsil in district["tehsils"].values():
            # Pairing logic
            if len(tehsil["trainers"]) > 1:
                tehsil["isPair"] = True
                top_performers = sum(1 for t in tehsil["trainers"] if t["isTopPerformer"])
                if top_performers == len(tehsil["trainers"]):
                    tehsil["pairStatus"] = "GREEN"
                elif top_performers > 0:
                    tehsil["pairStatus"] = "YELLOW"
                else:
                    tehsil["pairStatus"] = "RED"
            
            # Aggregate stats
            district["totalTrainers"] += len(tehsil["trainers"])
            for trainer in tehsil["trainers"]:
                if trainer["ruralUrban"] == 'Rural':
                    district["ruralCount"] += 1
                elif trainer["ruralUrban"] == 'Urban':
                    district["urbanCount"] += 1
            
            # Add unique headcounts
            if tehsil["trainers"]:
                tehsil_head_counts.add(tehsil["trainers"][0]["headCount"])
        
        district["totalHeadCount"] = sum(tehsil_head_counts)

    # --- 4. Save to JSON file ---
    with open(output_path, 'w') as f:
        json.dump(districts_data, f, indent=4)
    
    print(f"✅ Successfully created '{output_path}' with data for {len(districts_data)} districts.")


# --- HOW TO RUN ---
# 1. Make sure you have pandas and openpyxl installed:
#    pip install pandas openpyxl
# 2. Place your 'DFLT_Mapping.xlsx' file in the same directory as this script.
# 3. Run the script from your terminal: python your_script_name.py

if __name__ == '__main__':
    # Assuming the Excel file is in the same directory as the script
    excel_file_path = 'DFLT_Mapping.xlsx'
    create_data_json(excel_file_path)

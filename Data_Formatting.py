import pandas as pd
import json
import os
from datetime import datetime

def create_data_json(file_path, output_path):
    """
    Reads, cleans, validates, and processes trainer data from multiple provincial sheets,
    handling special vacancy rules, and saves a clean JSON file and a detailed log file.
    """
    
    # --- SETUP ---
    log_messages = []
    log_messages.append(f"--- Processing started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

    sheets_map = {
        'ASPCs_Punjab': 'Punjab',
        'ASPCs_KPK': 'KPK',
        'ASPCs_Sindh': 'Sindh'
    }
    
    all_dataframes = []
    
    log_messages.append("\n--- Phase 1: Loading Excel Sheets ---")
    for sheet_name, province_name in sheets_map.items():
        try:
            df_sheet = pd.read_excel(file_path, sheet_name=sheet_name)
            df_sheet['Province'] = province_name
            all_dataframes.append(df_sheet)
            log_messages.append(f"[SUCCESS] Loaded sheet: '{sheet_name}' with {len(df_sheet)} rows.")
        except Exception as e:
            log_messages.append(f"[WARNING] Could not process sheet '{sheet_name}'. Reason: {e}")
            continue

    if not all_dataframes:
        log_messages.append("[ERROR] No data could be loaded. Aborting.")
        return log_messages

    master_df = pd.concat(all_dataframes, ignore_index=True)
    log_messages.append(f"Total rows from all sheets: {len(master_df)}")

    # --- 2. Clean and Standardize Data ---
    log_messages.append("\n--- Phase 2: Cleaning and Standardizing Data ---")
    master_df['Under Consideration?'] = pd.to_numeric(master_df['Under Consideration?'], errors='coerce').fillna(0)
    master_df['Total Head Count'] = pd.to_numeric(master_df['Total Head Count'], errors='coerce').fillna(0).astype(int)
    for col in ['NAME', 'DISTRICT', 'DUTY STATION(TEHSIL)', 'Rural/Urban', 'Top_Performer?']:
        if col in master_df.columns:
            master_df[col] = master_df[col].astype(str).fillna('Unknown').str.strip()
    log_messages.append("[SUCCESS] Data types standardized and whitespace stripped.")

    # --- 3. Filter for records to be processed ---
    considered_df = master_df[master_df['Under Consideration?'].isin([1, 2])].copy()
    log_messages.append(f"\n--- Phase 3: Filtering Records ---")
    log_messages.append(f"Found {len(considered_df)} records marked for consideration (status 1 or 2).")
    
    expected_headcount = considered_df['Total Head Count'].sum()
    log_messages.append(f"[VALIDATION] Sum of 'Total Head Count' from all considered rows: {expected_headcount:,}")

    # --- 4. Process Individual Records ---
    log_messages.append("\n--- Phase 4: Processing Individual Records ---")
    districts_data = {}
    skipped_row_count = 0

    for index, record in considered_df.iterrows():
        name = record.get('NAME', 'Unknown'); province = record.get('Province', 'Unknown')
        district_name = record.get('DISTRICT', 'Unknown'); tehsil_name = record.get('DUTY STATION(TEHSIL)', 'Unknown')
        consideration_status = record.get('Under Consideration?'); head_count = record.get('Total Head Count', 0)
        
        log_messages.append(f"\nProcessing row {index+2} | Name: {name} | District: {district_name} | HC: {head_count} | Status: {consideration_status}")

        if district_name in ['Unknown', 'nan', ''] or tehsil_name in ['Unknown', 'nan', '']:
            log_messages.append(f"  [SKIPPED] Missing District or Tehsil name.")
            skipped_row_count += 1
            continue
        
        if district_name not in districts_data: districts_data[district_name] = {"name": district_name, "province": province, "tehsils": {}}
        if tehsil_name not in districts_data[district_name]["tehsils"]: districts_data[district_name]["tehsils"][tehsil_name] = {"name": tehsil_name, "district": district_name, "coords": [0,0], "trainers": []}
        
        try:
            lat = float(str(record.get('Latitude')).split('°')[0]); lon = float(str(record.get('Longitude')).split('°')[0])
            districts_data[district_name]["tehsils"][tehsil_name]['coords'] = [lat, lon]
        except (ValueError, TypeError): log_messages.append(f"  [WARNING] Invalid coordinates for this row.")

        is_vacant_row = 'vacant' in name.lower()
        trainer = { "name": name, "cnic": str(record.get('CNIC')), "headCount": head_count,
                    "isTopPerformer": 'Top Performer' in record.get('Top_Performer?'),
                    "ruralUrban": record.get('Rural/Urban'), "isVacant": False }

        if is_vacant_row:
            trainer['isVacant'] = True; trainer['name'] = 'Vacant Position'
            districts_data[district_name]["tehsils"][tehsil_name]["trainers"].append(trainer)
            log_messages.append(f"  [ACTION] Added 1 'Vacant Position' (from Name column).")
        elif consideration_status == 2:
            districts_data[district_name]["tehsils"][tehsil_name]["trainers"].append(trainer)
            vacant_trainer = trainer.copy(); vacant_trainer['name'] = 'Vacant Position'; vacant_trainer['isVacant'] = True; vacant_trainer['headCount'] = 0
            districts_data[district_name]["tehsils"][tehsil_name]["trainers"].append(vacant_trainer)
            log_messages.append(f"  [ACTION] Added trainer '{name}' AND 1 'Vacant Position' (due to Status 2).")
        else:
            districts_data[district_name]["tehsils"][tehsil_name]["trainers"].append(trainer)
            log_messages.append(f"  [ACTION] Added standard trainer '{name}'.")

    # --- 5. Final Calculations & Aggregation ---
    log_messages.append("\n--- Phase 5: Aggregating Final Statistics ---")
    final_calculated_headcount = 0
    for district in districts_data.values():
        all_trainers_in_district = [t for tehsil in district["tehsils"].values() for t in tehsil['trainers']]
        real_trainers_in_district = [t for t in all_trainers_in_district if not t.get('isVacant')]
        
        district["totalHeadCount"] = sum(t.get('headCount', 0) for t in all_trainers_in_district)
        district["totalTrainers"] = len(real_trainers_in_district)
        district["ruralCount"] = sum(1 for t in real_trainers_in_district if t.get('ruralUrban') == 'Rural')
        district["urbanCount"] = sum(1 for t in real_trainers_in_district if t.get('ruralUrban') == 'Urban')

        final_calculated_headcount += district["totalHeadCount"]
        
        for tehsil in district["tehsils"].values():
            real_trainers = [t for t in tehsil['trainers'] if not t.get('isVacant')]
            vacant_slots = [t for t in tehsil['trainers'] if t.get('isVacant')]
            if len(real_trainers) > 0 and len(vacant_slots) > 0: tehsil['vacancyStatus'] = 'PARTIAL'
            elif len(real_trainers) == 0 and len(vacant_slots) > 0: tehsil['vacancyStatus'] = 'FULL'
            else: tehsil['vacancyStatus'] = 'NONE'
            tehsil["isPair"] = len(real_trainers) > 1
            if tehsil["isPair"]:
                top_performers = sum(1 for t in real_trainers if t["isTopPerformer"])
                if top_performers == len(real_trainers): tehsil["pairStatus"] = "GREEN"
                elif top_performers > 0: tehsil["pairStatus"] = "YELLOW"
                else: tehsil["pairStatus"] = "RED"

    # --- 6. Final Report and Save ---
    log_messages.append("\n--- Phase 6: Final Summary ---")
    log_messages.append(f"Total Rows Considered: {len(considered_df)}")
    log_messages.append(f"Total Rows Skipped (due to missing data): {skipped_row_count}")
    log_messages.append(f"Total Districts Processed: {len(districts_data)}")
    log_messages.append(f"Expected Total Headcount (from source file): {expected_headcount:,}")
    log_messages.append(f"Final Calculated Headcount (in JSON): {final_calculated_headcount:,}")

    if expected_headcount == final_calculated_headcount:
        log_messages.append("\n[SUCCESS] Validation successful! The final headcount matches the source data.")
    else:
        log_messages.append("\n[ERROR] Validation failed! Please review the logs for skipped rows or data errors.")

    with open(output_path, 'w') as f: json.dump(districts_data, f, indent=4)
    log_messages.append(f"✅ Successfully created '{output_path}'")
    
    return log_messages

if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    excel_file_path = os.path.join(script_dir, 'DFLT Phase_2_Mapping.xlsx') 
    json_output_path = os.path.join(script_dir, 'data.json')
    log_file_path = os.path.join(script_dir, 'processing_log.txt')
    
    logs = create_data_json(excel_file_path, json_output_path)
    
    with open(log_file_path, 'w', encoding='utf-8') as f: f.write("\n".join(logs))
    
    # FIX: This block now safely prints the summary without crashing.
    try:
        summary_start_index = logs.index('--- Phase 6: Final Summary ---')
        print("\n" + "\n".join(logs[summary_start_index:]))
    except ValueError:
        # If the script failed early, print all available logs
        print("\n".join(logs))

    print(f"\nDetailed log saved to '{log_file_path}'")

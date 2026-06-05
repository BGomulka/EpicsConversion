#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import sys
from pathlib import Path
import argparse
import time

try:
    import pandas as pd
except ImportError:
    print("Error: The 'pandas' library is required. Install it using 'pip install pandas openpyxl'.")
    sys.exit(1)

def generate_epics_db(df, output_db_path):
    db_lines = []
    
    for _, row in df.iterrows():
        if pd.isna(row.get('Record Type')) or pd.isna(row.get('Record Name')):
            continue
            
        rec_type = str(row['Record Type']).strip()
        rec_name = str(row['Record Name']).strip()
        
        if not rec_type or not rec_name or rec_type.lower() == 'nan':
            continue
            
        db_lines.append(f'record({rec_type}, "{rec_name}") {{')
        
        for col in df.columns:
            if col in ['Record Type', 'Record Name', 'Source File']:
                continue
                
            val = row[col]
            if pd.isna(val):
                continue
                
            if isinstance(val, float) and val.is_integer():
                val = int(val)
                
            val_str = str(val).strip()
            
            if not val_str:
                continue
                
            is_disabled = False
            if val_str.startswith('#'):
                is_disabled = True
                val_str = val_str[1:].strip()
                
            comment = ""
            in_quotes = False
            i = 0
            while i < len(val_str):
                if val_str[i] == '"':
                    in_quotes = not in_quotes
                elif val_str[i] == '#' and not in_quotes:
                    comment = val_str[i:].strip()
                    val_str = val_str[:i].strip()
                    break
                i += 1
                
            prefix = "    # field" if is_disabled else "    field"
            suffix = f" {comment}" if comment else ""
            
            db_lines.append(f'{prefix}({col}, {val_str}){suffix}')
                
        db_lines.append('}\n') 
    
    with open(output_db_path, 'w') as f:
        f.write('\n'.join(db_lines))

def parse_db_to_dataframe(db_path, source_file_name=""):
    with open(db_path, 'r') as f:
        content = f.read()
    
    record_pattern = re.compile(r'^[ \t]*record\s*\(\s*([a-zA-Z0-9_]+)\s*,\s*"([^"]+)"\s*\)\s*\{(.*?)\}', re.MULTILINE | re.DOTALL)
    field_pattern = re.compile(r'^[ \t]*(#?)[ \t]*field\s*\(\s*([a-zA-Z0-9_]+)\s*,\s*((?s:".*?")|[^)]+?)\s*\)[ \t]*(#.*)?', re.MULTILINE)
    
    data = []
    
    for rec_match in record_pattern.finditer(content):
        rec_type = rec_match.group(1)
        rec_name = rec_match.group(2)
        body = rec_match.group(3)
        
        record_dict = {
            'Record Type': rec_type,
            'Record Name': rec_name
        }
        
        if source_file_name:
            record_dict['Source File'] = source_file_name
        
        for f_match in field_pattern.finditer(body):
            is_disabled = bool(f_match.group(1))
            field_name = f_match.group(2)
            field_val = f_match.group(3).strip() 
            comment = f_match.group(4)
            
            excel_val = field_val
            if comment:
                excel_val = f"{excel_val} {comment}"
            if is_disabled:
                excel_val = f"# {excel_val}"
                
            record_dict[field_name] = excel_val
            
        data.append(record_dict)
            
    return pd.DataFrame(data)

def process_db_directory(input_dir_path, output_dir_path, combine=False):
    input_dir = Path(input_dir_path)
    output_dir = Path(output_dir_path)
    
    if not input_dir.is_dir():
        print(f"Error: Source directory '{input_dir}' does not exist.")
        return
        
    output_dir.mkdir(parents=True, exist_ok=True)
    
    db_files = list(input_dir.glob('*.db'))
    if not db_files:
        print(f"No .db files found in {input_dir}")
        return
        
    print(f"Found {len(db_files)} .db file(s). Starting DB -> Excel conversion...")
    
    if combine:
        all_dfs = []
        for db_path in db_files:
            try:
                df = parse_db_to_dataframe(db_path, source_file_name=db_path.name)
                if not df.empty:
                    all_dfs.append(df)
            except Exception as e:
                print(f"  -> Unexpected Error processing {db_path.name}: {e}")
        
        if all_dfs:
            combined_df = pd.concat(all_dfs, ignore_index=True)
            
            cols = combined_df.columns.tolist()
            if 'Source File' in cols:
                cols.insert(2, cols.pop(cols.index('Source File')))
                combined_df = combined_df[cols]
                
            output_path = output_dir / "combined_output.xlsx"
            combined_df.to_excel(output_path, index=False, engine='openpyxl')
            print(f"Combined output saved to: {output_path}")
    else:
        for db_path in db_files:
            output_filename = db_path.with_suffix('.xlsx').name
            output_path = output_dir / output_filename
            print(f"Converting: {db_path.name} -> {output_filename}")
            
            try:
                df = parse_db_to_dataframe(db_path)
                if df.empty:
                    print(f"  -> Warning: No valid records parsed from {db_path.name}. Skipping.")
                    continue
                df.to_excel(output_path, index=False, engine='openpyxl')
            except (FileNotFoundError, PermissionError) as io_err:
                print(f"  -> File Access Error processing {db_path.name}: {io_err}")
            except Exception as e:
                print(f"  -> Unexpected Error processing {db_path.name}: {e}")
            
    print("Batch conversion complete!\n")

def process_excel_directory(input_dir_path, output_dir_path, split=False):
    input_dir = Path(input_dir_path)
    output_dir = Path(output_dir_path)
    
    if not input_dir.is_dir():
        print(f"Error: Source directory '{input_dir}' does not exist.")
        return
        
    output_dir.mkdir(parents=True, exist_ok=True)
    
    excel_files = list(input_dir.glob('*.xlsx'))
    if not excel_files:
        print(f"No .xlsx files found in {input_dir}")
        return

    print(f"Found {len(excel_files)} Excel file(s). Starting Excel -> DB conversion...")
    for excel_path in excel_files:
        try:
            df = pd.read_excel(excel_path, engine='openpyxl')
            
            if split and 'Source File' in df.columns:
                grouped = df.groupby('Source File')
                for source_file, group_df in grouped:
                    source_name = str(source_file).strip()
                    if not source_name.endswith('.db'):
                        source_name += '.db'
                    output_path = output_dir / source_name
                    print(f"Converting group from {excel_path.name} -> {source_name}")
                    generate_epics_db(group_df, output_path)
            else:
                output_filename = excel_path.with_suffix('.db').name
                output_path = output_dir / output_filename
                print(f"Converting: {excel_path.name} -> {output_filename}")
                generate_epics_db(df, output_path)
                
        except ValueError as ve:
            print(f"  -> Format Error: Ensure openpyxl is installed and the file is a valid .xlsx file. ({ve})")
        except (FileNotFoundError, PermissionError) as io_err:
            print(f"  -> File Access Error processing {excel_path.name}: {io_err}")
        except Exception as e:
            print(f"  -> Unexpected Error processing {excel_path.name}: {e}")
            
    print("Batch conversion complete!\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=".db and .xlsx conversion script")
    
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--xd", action="store_true", help="Convert Excel to DB")
    mode.add_argument("--dx", action="store_true", help="Convert DB to Excel")
    
    parser.add_argument("-i", "--source_directory", required=True, help="Path to input files")
    parser.add_argument("-o", "--output_directory", required=True, help="Path to save output")
    
    parser.add_argument("-c", "--combine", action="store_true", help="Combine multiple DBs into a single Excel file (only valid with --dx)")
    parser.add_argument("-s", "--split", action="store_true", help="Split a single Excel file into multiple DBs based on the Source File column (only valid with --xd)")
    
    args = parser.parse_args()
    
    if args.combine and not args.dx:
        parser.error("--combine can only be used with --dx")
    if args.split and not args.xd:
        parser.error("--split can only be used with --xd")
    
    start_time = time.time()
    
    if args.xd:
        process_excel_directory(args.source_directory, args.output_directory, split=args.split)
    elif args.dx:
        process_db_directory(args.source_directory, args.output_directory, combine=args.combine)

    elapsed_time = time.time() - start_time
    print(f"Total execution time: {elapsed_time:.2f} seconds")
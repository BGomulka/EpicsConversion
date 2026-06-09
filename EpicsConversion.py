#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import sys
import csv
from pathlib import Path
import argparse
import time
import logging

logging.basicConfig(level=logging.WARNING, format='%(message)s')
logger = logging.getLogger(__name__)

def write_csv(data_list, output_csv_path):
    if not data_list:
        return False
        
    headers = []
    for d in data_list:
        for k in d.keys():
            if k not in headers:
                headers.append(k)
                
    ordered_headers = ['Record Type', 'Record Name']
    if 'Source File' in headers:
        ordered_headers.append('Source File')
    for h in headers:
        if h not in ordered_headers:
            ordered_headers.append(h)

    with open(output_csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=ordered_headers)
        writer.writeheader()
        writer.writerows(data_list)
    return True

def generate_epics_db(data_list, output_db_path):
    db_lines = []
    
    for row in data_list:
        rec_type = str(row.get('Record Type', '')).strip()
        rec_name = str(row.get('Record Name', '')).strip()
        
        if not rec_type or not rec_name or rec_type.lower() == 'nan':
            continue
            
        db_lines.append(f'record({rec_type}, "{rec_name}") {{')
        
        for col, val in row.items():
            if col in ['Record Type', 'Record Name', 'Source File']:
                continue
                
            if val is None:
                continue
                
            val_str = str(val).strip()
            if not val_str or val_str.lower() == 'nan':
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
    
    if not db_lines:
        return False

    with open(output_db_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(db_lines))
    return True

def parse_db_to_dicts(db_path, source_file_name=""):
    with open(db_path, 'r', encoding='utf-8') as f:
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
            
            csv_val = field_val
            if comment:
                csv_val = f"{csv_val} {comment}"
            if is_disabled:
                csv_val = f"# {csv_val}"
                
            record_dict[field_name] = csv_val
            
        data.append(record_dict)
            
    return data

def resolve_files(input_path, is_batch, is_test, ext):
    in_p = Path(input_path).resolve() if input_path else Path.cwd()
    files = []
    
    if is_batch:
        if in_p.is_dir():
            files = list(in_p.rglob(f"*{ext}"))
        else:
            logger.error(f"Error: Batch mode requires a directory. '{in_p}' is a file.")
            sys.exit(1)
    else:
        if in_p.is_file() and in_p.suffix == ext:
            files = [in_p]
        elif in_p.is_dir():
            found = list(in_p.glob(f"*{ext}"))
            if found:
                files = [found[0]]
                logger.info(f"Single file mode: Auto-selected first valid file '{files[0].name}'.")
            
    if is_test:
        files = [f for f in files if f.name.lower().startswith("test")]
        if not files:
            logger.error("\n[ERROR] Test mode validation failed! No files starting with 'test' found.")
            sys.exit(1)
            
    return sorted(list(set(files))), in_p

def process_db_to_csv(args, base_output):
    input_files, input_dir = resolve_files(args.input, args.batch, args.test, '.db')
    
    if not input_files:
        logger.error("No valid .db files found to process.")
        return
        
    logger.info(f"Found {len(input_files)} .db file(s). Starting DB -> CSV conversion...\n")
    success_count = 0
    
    if args.combine:
        all_data = []
        for db_path in input_files:
            try:
                data = parse_db_to_dicts(db_path, source_file_name=db_path.name)
                if data:
                    all_data.extend(data)
            except Exception as e:
                logger.error(f"  -> Unexpected Error processing {db_path.name}: {e}")
        
        if all_data:
            output_path = base_output / "combined_output.csv"
            if write_csv(all_data, output_path):
                logger.info(f"Combined output saved to: {output_path}")
                success_count += len(input_files)
    else:
        for db_path in input_files:
            if args.batch:
                relative_path = db_path.relative_to(input_dir)
                target_subdir = base_output / relative_path.parent
            else:
                target_subdir = base_output
                
            target_subdir.mkdir(parents=True, exist_ok=True)
            output_filename = db_path.with_suffix('.csv').name
            output_path = target_subdir / output_filename
            
            logger.info(f"Converting: {db_path.name} -> {output_filename}")
            try:
                data = parse_db_to_dicts(db_path)
                if not data:
                    logger.warning(f"  -> Warning: No valid records parsed from {db_path.name}. Skipping.")
                    continue
                if write_csv(data, output_path):
                    logger.info("  Status: Successfully converted")
                    success_count += 1
            except Exception as e:
                logger.error(f"  -> Unexpected Error processing {db_path.name}: {e}")
    
    return len(input_files), success_count

def process_csv_to_db(args, base_output):
    input_files, input_dir = resolve_files(args.input, args.batch, args.test, '.csv')
    
    if not input_files:
        logger.error("No valid .csv files found to process.")
        return
        
    logger.info(f"Found {len(input_files)} CSV file(s). Starting CSV -> DB conversion...\n")
    success_count = 0

    for csv_path in input_files:
        try:
            with open(csv_path, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                data = list(reader)
            
            if args.split and any('Source File' in d for d in data):
                grouped = {}
                for row in data:
                    src = row.get('Source File', 'unknown_source.db')
                    if not src.endswith('.db'):
                        src += '.db'
                    grouped.setdefault(src, []).append(row)
                
                for source_name, group_data in grouped.items():
                    target_subdir = base_output
                    if args.batch:
                        relative_path = csv_path.relative_to(input_dir)
                        target_subdir = base_output / relative_path.parent
                    target_subdir.mkdir(parents=True, exist_ok=True)
                    
                    output_path = target_subdir / source_name
                    logger.info(f"Converting group from {csv_path.name} -> {source_name}")
                    if generate_epics_db(group_data, output_path):
                        success_count += 1
            else:
                target_subdir = base_output
                if args.batch:
                    relative_path = csv_path.relative_to(input_dir)
                    target_subdir = base_output / relative_path.parent
                target_subdir.mkdir(parents=True, exist_ok=True)
                
                output_filename = csv_path.with_suffix('.db').name
                output_path = target_subdir / output_filename
                logger.info(f"Converting: {csv_path.name} -> {output_filename}")
                if generate_epics_db(data, output_path):
                    logger.info("  Status: Successfully converted")
                    success_count += 1
                    
        except Exception as e:
            logger.error(f"  -> Unexpected Error processing {csv_path.name}: {e}")
            
    return len(input_files), success_count

def process_pipeline(args):
    start_time = time.time()
    
    if args.verbose:
        logger.setLevel(logging.INFO)

    base_output = Path(args.output).resolve() if args.output else Path.cwd()
    
    if args.test:
        final_output_root = base_output / "test"
    elif args.folder_name:
        final_output_root = base_output / args.folder_name
    else:
        final_output_root = base_output

    final_output_root.mkdir(parents=True, exist_ok=True)

    if args.cd:
        result = process_csv_to_db(args, final_output_root)
    elif args.dc:
        result = process_db_to_csv(args, final_output_root)
        
    if result and args.verbose:
        total_files, success_count = result
        elapsed_time = time.time() - start_time
        logger.info("\n" + "="*60)
        logger.info("EXECUTION DETAILS SUMMARY")
        logger.info("="*60)
        logger.info(f"Conversion Type:          {'CSV -> DB' if args.cd else 'DB -> CSV'}")
        logger.info(f"Total Files Processed:    {total_files}")
        logger.info(f"Total Success:            {success_count}")
        logger.info(f"Output Root Directory:    {final_output_root}")
        logger.info(f"Test Mode Active:         {args.test}")
        logger.info(f"Batch Mode Active:        {args.batch}")
        logger.info(f"Total Execution Time:     {elapsed_time:.2f} seconds")
        logger.info("="*60 + "\n")
        
    print("Complete")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=".db and .csv conversion script")
    
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--cd", action="store_true", help="Convert CSV to DB")
    mode.add_argument("--dc", action="store_true", help="Convert DB to CSV")
    
    parser.add_argument("-i", "--input", default=None, help="Path to input file/folder (Defaults to CWD)")
    parser.add_argument("-o", "--output", default=None, help="Path to save output (Defaults to CWD)")
    parser.add_argument("-b", "--batch", action="store_true", help="Process directories recursively instead of a single file")
    parser.add_argument("-f", "--folder_name", default=None, help="Optional: Create a specific folder inside the output directory")
    parser.add_argument("-t", "--test", action="store_true", help="Run in test mode (only processes files starting with 'test')")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable detailed logging output")
    
    parser.add_argument("-c", "--combine", action="store_true", help="Combine multiple DBs into a single CSV (only valid with --dc)")
    parser.add_argument("-s", "--split", action="store_true", help="Split a single CSV into multiple DBs based on Source File column (only valid with --cd)")
    
    args = parser.parse_args()
    
    if args.combine and not args.dc:
        parser.error("--combine can only be used with --dc")
    if args.split and not args.cd:
        parser.error("--split can only be used with --cd")
    
    try:
        process_pipeline(args)
    except Exception as err:
        logger.error(err)
        sys.exit(1)
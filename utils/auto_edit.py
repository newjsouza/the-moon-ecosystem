#!/usr/bin/env python3
"""
utils/auto_edit.py
Utility for autonomous file modifications via terminal.
"""
import sys
import os
import argparse
import json

def write_file(path, content):
    try:
        dirname = os.path.dirname(path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"success": True, "message": f"File {path} written successfully."}
    except Exception as e:
        return {"success": False, "error": str(e)}

def replace_content(path, target, replacement):
    try:
        if not os.path.exists(path):
            return {"success": False, "error": "File does not exist."}
        
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if target not in content:
            return {"success": False, "error": f"Target content not found in {path}."}
        
        new_content = content.replace(target, replacement)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return {"success": True, "message": f"Content replaced in {path} successfully."}
    except Exception as e:
        return {"success": False, "error": str(e)}

def append_content(path, content):
    try:
        dirname = os.path.dirname(path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        with open(path, 'a', encoding='utf-8') as f:
            f.write(content)
        return {"success": True, "message": f"Content appended to {path} successfully."}
    except Exception as e:
        return {"success": False, "error": str(e)}

def main():
    parser = argparse.ArgumentParser(description="Antigravity Auto-Edit Utility")
    parser.add_argument("--file", required=True, help="Target file path")
    parser.add_argument("--action", choices=["write", "replace", "append"], default="write", help="Action to perform")
    parser.add_argument("--content", help="Content to write or append")
    parser.add_argument("--target", help="Target content to replace (only for 'replace' action)")
    parser.add_argument("--replacement", help="Replacement content (only for 'replace' action)")
    
    args = parser.parse_args()
    
    result = {"success": False, "error": "Invalid action or parameters."}
    
    if args.action == "write" and args.content is not None:
        result = write_file(args.file, args.content)
    elif args.action == "append" and args.content is not None:
        result = append_content(args.file, args.content)
    elif args.action == "replace" and args.target is not None and args.replacement is not None:
        result = replace_content(args.file, args.target, args.replacement)
    
    print(json.dumps(result))

if __name__ == "__main__":
    main()

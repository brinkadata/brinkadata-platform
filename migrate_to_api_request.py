#!/usr/bin/env python3
"""
Migration script: Replace call_backend() with api_request() throughout app.py
Execution: python migrate_to_api_request.py
"""

import re
import sys

def migrate_app_py():
    """Migrate frontend/app.py to use centralized api_request()"""
    
    # Read original file
    with open('frontend/app.py', 'r', encoding='utf-8') as f:
        content = f.content()
    
    original_content = content
    
    # Step 1: Replace json_body parameter with json
    content = re.sub(r'json_body=', 'json=', content)
    
    # Step 2: Remove is_protected_path function (lines ~855-875)
    # Pattern: def is_protected_path through its return statement
    content = re.sub(
        r'def is_protected_path\(path: str\) -> bool:.*?return path not in public_paths\n\n',
        '',
        content,
        flags=re.DOTALL
    )
    
    # Step 3: Remove call_backend function (starts around line 878)
    # Pattern: def call_backend through end of function
    content = re.sub(
        r'def call_backend\(.*?\n(?=\ndef |\nclass |\n# -+\n)',
        '',
        content,
        flags=re.DOTALL
    )
    
    # Step 4: Remove call_backend_tracked function
    content = re.sub(
        r'def call_backend_tracked\(.*?\n(?=\ndef |\nclass |\n# -+\n)',
        '',
        content,
        flags=re.DOTALL
    )
    
    # Step 5: Replace all call_backend( with api_request(
    content = content.replace('call_backend(', 'api_request(')
    
    # Step 6: Replace all call_backend_tracked( with api_request(
    # Note: call_backend_tracked has different signature, need to adjust params
    # Old: call_backend_tracked(method, path, json_body=None, tracked_name=None, expects_auth=True, timeout=20)
    # New: api_request(method, path, json=None, params=None, timeout=30, _retry=True)
    
    # Remove tracked_name and expects_auth parameters
    content = re.sub(r',\s*tracked_name=[^,)]+', '', content)
    content = re.sub(r',\s*expects_auth=[^,)]+', '', content)
    
    # Replace call_backend_tracked( with api_request(
    content = content.replace('call_backend_tracked(', 'api_request(')
    
    # Step 7: Remove old BACKEND_URL usage - it's now in get_api_base_url()
    # Remove f"{BACKEND_URL}" usages (should not exist after using api_request)
    
    # Write migrated file
    with open('frontend/app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Count changes
    original_calls = len(re.findall(r'call_backend\(|call_backend_tracked\(', original_content))
    remaining_calls = len(re.findall(r'call_backend\(|call_backend_tracked\(', content))
    new_calls = len(re.findall(r'api_request\(', content))
    
    print(f"✓ Migration complete")
    print(f"  Original call_backend calls: {original_calls}")
    print(f"  Remaining call_backend calls: {remaining_calls}")
    print(f"  New api_request calls: {new_calls}")
    
    if remaining_calls > 0:
        print(f"  ⚠️  WARNING: {remaining_calls} call_backend calls still remain!")
        return False
    
    return True

if __name__ == "__main__":
    success = migrate_app_py()
    sys.exit(0 if success else 1)

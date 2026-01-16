#!/usr/bin/env python3
"""
Automatic DRY Refactoring Script

Bu script barcha handler'lardagi session boilerplate'ni avtomatik topib,
decorator bilan almashtiradi.

ISHLATISH:
    python scripts/auto_refactor_handlers.py

XAVFSIZLIK:
    - Faqat dry-run mode (o'zgarishlarni ko'rsatadi, faylga yozmaydi)
    - Manual review kerak
"""

import os
import re
from pathlib import Path

# Handler directories
DRIVER_HANDLERS = Path("/Users/baxrom/URDU_ISH/taksi/app/bot/handlers/driver")
PASSENGER_HANDLERS = Path("/Users/baxrom/URDU_ISH/taksi/app/bot/handlers/passenger")

# Patterns to detect
SESSION_PATTERN = r"async with get_session\(\) as session:"
DRIVER_FETCH_PATTERN = r"driver = await get_driver_(by_user_id|or_error)\(session, user_id"
PASSENGER_FETCH_PATTERN = r"passenger = await get_passenger_(by_user_id|or_error)\(session, user_id"


def analyze_file(filepath):
    """Analyze a file for refactoring opportunities"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    has_session_boilerplate = bool(re.search(SESSION_PATTERN, content))
    has_driver_fetch = bool(re.search(DRIVER_FETCH_PATTERN, content))
    has_passenger_fetch = bool(re.search(PASSENGER_FETCH_PATTERN, content))
    
    # Count handlers
    handler_count = len(re.findall(r'@router\.(message|callback_query)', content))
    
    # Check if decorator already imported
    has_decorator_import = 'from app.bot.decorators import' in content
    
    return {
        'filepath': filepath,
        'has_boilerplate': has_session_boilerplate,
        'handler_type': 'driver' if has_driver_fetch else ('passenger' if has_passenger_fetch else 'mixed'),
        'handler_count': handler_count,
        'has_decorator': has_decorator_import,
        'needs_refactor': has_session_boilerplate and not has_decorator_import
    }


def scan_directory(directory, category):
    """Scan directory for Python files"""
    results = []
    for file in directory.glob("*.py"):
        if file.name == '__init__.py':
            continue
        
        analysis = analyze_file(file)
        analysis['category'] = category
        results.append(analysis)
    
    return results


def main():
    """Main function"""
    print("=" * 60)
    print("🔍 DRY REFACTORING ANALYSIS")
    print("=" * 60)
    print()
    
    # Scan both directories
    driver_results = scan_directory(DRIVER_HANDLERS, 'driver')
    passenger_results = scan_directory(PASSENGER_HANDLERS, 'passenger')
    
    all_results = driver_results + passenger_results
    
    # Summary
    needs_refactor = [r for r in all_results if r['needs_refactor']]
    already_done = [r for r in all_results if r['has_decorator']]
    
    print(f"📊 SUMMARY:")
    print(f"   Total files: {len(all_results)}")
    print(f"   ✅ Already refactored: {len(already_done)}")
    print(f"   ⏳ Needs refactoring: {len(needs_refactor)}")
    print(f"   ℹ️  No boilerplate: {len(all_results) - len(needs_refactor) - len(already_done)}")
    print()
    
    # Detail for files needing refactor
    if needs_refactor:
        print("📋 FILES NEEDING REFACTORING:")
        print()
        
        for result in needs_refactor:
            filepath = result['filepath']
            filename = filepath.name
            category = result['category']
            handler_count = result['handler_count']
            handler_type = result['handler_type']
            
            print(f"   📄 {category}/{filename}")
            print(f"      Handlers: {handler_count}")
            print(f"      Type: {handler_type}")
            print(f"      Decorator needed: @with_{handler_type}_session")
            print()
    
    # Already done
    if already_done:
        print("✅ ALREADY REFACTORED:")
        print()
        for result in already_done:
            filename = result['filepath'].name
            category = result['category']
            print(f"   ✓ {category}/{filename}")
        print()
    
    print("=" * 60)
    print("💡 RECOMMENDATION:")
    print("=" * 60)
    print()
    print(f"Refactor {len(needs_refactor)} files to:")
    print("  1. Add decorator import")
    print("  2. Update handler signatures")
    print("  3. Remove session boilerplate")
    print()
    print(f"Expected impact: -{len(needs_refactor) * 10} lines of boilerplate")
    print()


if __name__ == "__main__":
    main()

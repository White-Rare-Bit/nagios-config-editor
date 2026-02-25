#!/usr/bin/env python3
"""
Test script for object reordering via staging API.

Simulates the frontend reordering flow:
1. Create a test config file with multiple objects
2. Stage multiple moves to reorder them
3. Check what the staging state looks like
4. Apply the changes
5. Verify the final order in the config file
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nagios_parser import NagiosConfigParser
from nagios_service import NagiosService
from staging_manager import StagingManager


def create_test_config(config_dir: str) -> str:
    """Create a test config file with 7 hostgroups in a specific order."""
    config_file = os.path.join(config_dir, "hostgroups.cfg")

    # Create hostgroups in order: A, B, C, D, E, F, G
    content = """# Test hostgroups config

define hostgroup {
    hostgroup_name    group-A
    alias             Group A - First
}

define hostgroup {
    hostgroup_name    group-B
    alias             Group B - Second
}

define hostgroup {
    hostgroup_name    group-C
    alias             Group C - Third
}

define hostgroup {
    hostgroup_name    group-D
    alias             Group D - Fourth
}

define hostgroup {
    hostgroup_name    group-E
    alias             Group E - Fifth
}

define hostgroup {
    hostgroup_name    group-F
    alias             Group F - Sixth
}

define hostgroup {
    hostgroup_name    group-G
    alias             Group G - Seventh
}
"""
    with open(config_file, 'w') as f:
        f.write(content)

    return config_file


def get_object_order(service: NagiosService, config_file: str) -> list:
    """Get the current order of hostgroup names in the config file."""
    service.reload()
    all_objects = service.get_objects()
    print(f"  DEBUG: Total objects parsed: {len(all_objects)}")
    if all_objects:
        print(f"  DEBUG: First object source_file: {all_objects[0].source_file}")
        print(f"  DEBUG: Looking for config_file: {config_file}")

    # Normalize paths for comparison
    config_file_real = os.path.realpath(config_file)
    objects = [o for o in all_objects
               if os.path.realpath(o.source_file) == config_file_real and o.object_type == 'hostgroup']
    objects.sort(key=lambda o: o.line_number)
    return [o.attributes.get('hostgroup_name') for o in objects]


def build_staged_moves(service: NagiosService, config_file: str, new_order: list) -> list:
    """
    Build staged moves array to reorder objects into new_order.

    This simulates what the frontend sends: an array of moves sorted by insertPosition.
    """
    service.reload()
    config_file_real = os.path.realpath(config_file)
    objects = [o for o in service.get_objects()
               if os.path.realpath(o.source_file) == config_file_real and o.object_type == 'hostgroup']

    # Build a lookup by name
    obj_by_name = {o.attributes.get('hostgroup_name'): o for o in objects}

    moves = []
    for i, name in enumerate(new_order):
        obj = obj_by_name.get(name)
        if not obj:
            print(f"WARNING: Object {name} not found")
            continue

        # Build stable key like frontend does: source_file|object_type|display_name
        stable_key = f"{obj.source_file}|{obj.object_type}|{obj.get_display_name()}"

        # insertPosition is the desired order (lower = earlier in file)
        # Frontend uses fractional values, we'll use simple integers
        insert_position = (i + 1) * 10  # 10, 20, 30, ...

        move = {
            'stableKey': stable_key,
            'targetFile': config_file,
            'originalFile': obj.source_file,
            'insertPosition': insert_position,
            'object': {
                'source_file': obj.source_file,
                'object_type': obj.object_type,
                'line_number': obj.line_number,
                'attributes': dict(obj.attributes),
                'name': name,
                'display_name': name
            }
        }
        moves.append(move)

    # Sort by insertPosition (frontend does this before sending)
    moves.sort(key=lambda m: m.get('insertPosition', 0))

    return moves


def print_separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def print_config_content(config_file: str):
    """Print the actual config file content."""
    with open(config_file, 'r') as f:
        content = f.read()
    print(content)


def run_test():
    """Run the reordering test."""

    # Create temp directory for test
    test_dir = tempfile.mkdtemp(prefix='nagios_reorder_test_')
    print(f"Test directory: {test_dir}")

    try:
        # Setup
        print_separator("1. SETUP: Creating test config")
        config_file = create_test_config(test_dir)

        staging_file = os.path.join(test_dir, 'staging.json')
        sm = StagingManager(staging_file)
        service = NagiosService(test_dir, staging_manager=sm)

        initial_order = get_object_order(service, config_file)
        print(f"Initial order: {initial_order}")
        print(f"Expected: ['group-A', 'group-B', 'group-C', 'group-D', 'group-E', 'group-F', 'group-G']")

        print("\nInitial config file content:")
        print_config_content(config_file)

        # Define new order - move things around significantly
        # Original: A, B, C, D, E, F, G
        # New:      E, C, G, A, F, B, D  (significant reordering)
        new_order = ['group-E', 'group-C', 'group-G', 'group-A', 'group-F', 'group-B', 'group-D']

        print_separator("2. STAGING: Building staged moves")
        print(f"Target order: {new_order}")

        staged_moves = build_staged_moves(service, config_file, new_order)

        print(f"\nStaged moves ({len(staged_moves)} moves):")
        for i, move in enumerate(staged_moves):
            obj_name = move['object']['name']
            insert_pos = move['insertPosition']
            print(f"  {i+1}. {obj_name} (insertPosition={insert_pos})")

        print("\nFull staged moves data:")
        print(json.dumps(staged_moves, indent=2, default=str))

        # Convert list of moves to dict keyed by stable key (composite format)
        staged_moves_dict = {}
        for move in staged_moves:
            key = move['stableKey']
            staged_moves_dict[key] = {
                'targetFile': move['targetFile'],
                'insertPosition': move['insertPosition'],
                'object': move['object'],
            }

        # Build staging data like the frontend sends
        staging_data = {
            'sessionId': 'test-session',
            'userName': 'test-user',
            'userEmail': 'test@example.com',
            'pendingEdits': {},
            'stagedMoves': staged_moves_dict,
            'stagedCreations': [],
            'stagedObjectDeletions': [],
            'newFiles': [],
            'stagedFileCreations': [],
            'stagedFileDeletions': [],
            'stagedFileMoves': [],
            'stagedFolderCreations': [],
            'stagedFolderDeletions': [],
            'stagedFolderMoves': []
        }

        print_separator("3. APPLYING: Calling apply_object_composite")

        # Apply the moves
        result = service.apply_object_composite(staging_data)

        print(f"Result success: {result.success}")
        print(f"Result data: {json.dumps(result.data, indent=2, default=str)}")

        if result.data.get('errors'):
            print(f"\nERRORS:")
            for err in result.data['errors']:
                print(f"  - {err}")

        print_separator("4. VERIFICATION: Checking final order")

        final_order = get_object_order(service, config_file)
        print(f"Expected order: {new_order}")
        print(f"Actual order:   {final_order}")

        # Check if order matches
        if final_order == new_order:
            print("\n✓ SUCCESS: Order matches expected!")
        else:
            print("\n✗ FAILURE: Order does not match!")
            print("\nDifferences:")
            for i, (expected, actual) in enumerate(zip(new_order, final_order)):
                status = "✓" if expected == actual else "✗"
                print(f"  Position {i+1}: expected={expected}, actual={actual} {status}")

        print_separator("5. FINAL CONFIG FILE CONTENT")
        print_config_content(config_file)

        # Extract just the hostgroup_name lines for easy comparison
        print_separator("6. SUMMARY: Order comparison")
        print(f"Initial: {['group-A', 'group-B', 'group-C', 'group-D', 'group-E', 'group-F', 'group-G']}")
        print(f"Target:  {new_order}")
        print(f"Result:  {final_order}")

        return final_order == new_order

    finally:
        # Cleanup
        print(f"\nCleaning up test directory: {test_dir}")
        shutil.rmtree(test_dir)


if __name__ == '__main__':
    success = run_test()
    sys.exit(0 if success else 1)

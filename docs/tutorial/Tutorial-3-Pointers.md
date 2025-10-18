# Memory Hack Tutorial 3 — Pointer Tools

This tutorial explains the purpose of the Pointer tools and how to use them. It focuses on what each tool does and the general workflow, without examples or screenshots.

## What Pointers Are For
- Direct addresses often change when a game restarts, loads a new level, or after an update.
- Pointer chains let you resolve a changing address by following a sequence of memory reads from a stable base (typically a module or otherwise static region) plus a series of offsets.
- Compared with AOB patterns:
  - Pointers are “address that points to address,” then add offsets at each hop until you reach your value.
  - AOB is “pattern + offset” found by scanning memory for a stable byte signature. Either approach can be appropriate; pointers are best when there is a consistent chain anchored to a static region.

The Pointer tools provide three capabilities:
- Pointer Scanner — discover candidate pointer chains to a known address.
- Pointer Verify — check which pointers from a saved file still resolve to the current address.
- Pointer Offset — compute the final hop offset for a known pointer chain when you know the target address.

Saved files live under your user scripts folder. For the Pointer Scanner and Verify tools, files are stored in:
- memory_hack/user_scripts/pointer/pointerscanner/<AppName>.ptr

## Pointer Scanner
Finds pointer chains that resolve to a known target address and saves them to a .ptr file for later reuse.

Inputs
- Address — The current address of the value you want to reach. Accepts either a hex address (e.g., 7FF6ABCD1234) or a path form ModuleName.ext:mapIndex+offset (e.g., Terraria.exe:0+1A2B3C).
- Maximum Offset — The maximum byte distance to consider for each hop (default 4096). Lower values constrain results to nearby pointers and reduce noise.
- Negative Offsets — Allow offsets to be negative. Leave off unless you have reason to include backwards references.
- Maximum Depth — How many hops deep to search (1–10). Start small (2–3) and increase if needed.
- Search Regions — Which mapped memory regions to search (e.g., specific modules, heap, or all regions). Choosing likely regions first can speed scanning and improve relevance.

Operation
- The scanner searches for 64-bit values that fall within ±Maximum Offset of your target (or the previous hop), then iteratively repeats up to the selected Depth.
- Candidates are filtered for alignment and for plausibility using the process’s mapped regions; static addresses (module-backed) are preferred as anchors.
- Results are organized as chains rooted at a base region (with path and map index) and written to <AppName>.ptr.

Output (.ptr) structure (conceptual)
- For each candidate pointer:
  - path — Module or mapping path the base pointer lives in.
  - node — mapIndex identifying which instance of that mapping.
  - base_offset — Offset into the base mapping where the chain begins.
  - offsets — List of hex offsets applied at each hop (last entry points to the final address).

Typical use
1) Attach to the game and obtain the current address of your value (see Tutorial 1).
2) Open Pointer Scanner, supply Address/Offset/Depth/Regions, and Start.
3) When finished, a <AppName>.ptr file is written to the pointerscanner directory.

## Pointer Verify
Checks a saved .ptr file against the current running process and a current known address. It filters to pointer chains that still resolve to the specified address now.

Inputs
- Pointer File — Select a <AppName>.ptr produced by the scanner.
- Current Address — The value’s current address (hex). This is your ground truth for verification.

Operation
- The tool maps each pointer’s base (path + mapIndex) to the current process map to rebuild a base address.
- It walks the pointer’s offsets (reading a 64-bit value and adding the next offset at each hop).
- If the final computed address equals the Current Address, the pointer is considered valid for this run.

Results
- Displays the number of valid pointers and lists the first set (up to a UI limit).
- Each listed pointer has a Copy action that places a Code List–ready object on the clipboard:
  - address — Module path form (ModuleName.ext:mapIndex+baseOffset)
  - offsets — Comma-separated hex offsets (e.g., 8, 28, 1C)

Using with the Code List
- Navigate to the Codes tab and paste from the clipboard.
- Choose Source = pointer, set the Address (path form) and Offsets; adjust Type/Signedness; then read, write, or freeze like a normal code.

## Pointer Offset
Computes the last hop offset for a pointer chain when you know both the pointer base chain and the final target address.

Inputs
- Pointer Address — The base pointer’s address; path form allowed (ModuleName.ext:mapIndex+offset) or hex.
- Pointer Offsets — The offsets for the chain so far, comma-separated hex (e.g., 8, 28, 0). The tool will recompute the last entry.
- Output Address — The final target address you want the chain to resolve to (hex or path).

Operation
- Reads the pointer chain up to (but not including) the last hop to find the base address at that point.
- Computes the required last offset as (Output Address − last-read base), with sanity checks (e.g., bounds).
- Produces a result with the same Pointer Address and a revised Offsets string containing the correct last hop.

Results
- Displays Result Address and Result Offsets (read-only) when valid; otherwise indicates the pointer is invalid (e.g., out-of-range, bad input, or failed reads).
- You can copy the result and use it directly in the Code List as a pointer code.

## Tips and Guidance
- Start with modest settings (Depth 2–3, Max Offset 4096) and refine. Very large offsets or deep chains produce many low-quality candidates and long scans.
- Prefer searching module regions and nearby data sections first; they yield more stable anchors than ephemeral heap regions.
- If verification yields zero valid pointers across restarts, consider the AOB approach instead; some targets aren’t reachable via stable pointer chains.
- Use the path address form (ModuleName.ext:mapIndex+offset) in Code List entries to keep pointers resilient to load address changes.

## Related
- Tutorial 1 — Search and Code List (finding the initial address)
- Tutorial 2 — AOB (pattern-based alternative when pointer chains are unstable)


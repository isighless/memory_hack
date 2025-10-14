import ctypes
import json
import math
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.helpers.directory_utils import codes_directory
from app.helpers.memory_utils import get_ctype
from app.script_common import BaseScript
from app.script_ui import controls
from app.script_ui.validators import address_match
from .results import StructureResultsGroup
from app.search.value import Value


logger = logging.getLogger(__name__)


SupportedTypes = {
    'byte_1', 'byte_2', 'byte_4', 'byte_8', 'float'
}


class StructureSearch(BaseScript):
    """Search for a structure by matching multiple known values at fixed offsets.

    Flow:
    - Select Process
    - Load Code List (.codes)
    - Enter known values for any fields (leave others blank)
    - Search → returns candidate base rows (addresses per field)
    - Use → applies addresses to the selected Code List on the Codes tab
    """

    def on_load(self):
        self.put_data("PROCESS", None)
        self.put_data("FILES", [])
        self.put_data("SELECTED_FILE", "_null")
        self.put_data("CODES", [])           # list of code dicts from file
        self.put_data("OFFSETS", [])         # offsets from anchor
        self.put_data("ANCHOR_INDEX", -1)
        self.put_data("KNOWN", {})           # index -> parsed value
        self.put_data("RESULT_ROWS", [])     # rows with addresses
        self.put_data("RESULT_INDEX", 0)
        self.put_data("SCAN_THREAD", None)
        self.put_data("SCAN_ACTIVE", False)
        self.put_data("SCAN_TOTAL", 0)
        self.put_data("SCAN_DONE", 0)
        self.put_data("SCAN_CANDIDATES", [])
        self.put_data("SCAN_LAST_DONE", -1)
        self.put_data("SCAN_STALL_COUNT", 0)

    def get_script_information(self):
        return {
            'title': "Structure Search",
            'author': "Silas Marrs",
            'version': '1.0.0'
        }

    def build_ui(self):
        # Pages
        instructions = self.ui.add_page(controls.Page(id='PAGE_INSTRUCTIONS'))
        ps_page = self.ui.add_page(controls.Page(id='PAGE_PROCESS'))
        file_page = self.ui.add_page(controls.Page(id='PAGE_FILE'))
        input_page = self.ui.add_page(controls.Page(id='PAGE_INPUT'))
        results_page = self.ui.add_page(controls.Page(id='PAGE_RESULTS'))

        self.ui.set_page_header(instructions, "How It Works")
        self.ui.set_page_header(ps_page, "Process Select")
        self.ui.set_page_header(file_page, "Load Code List")
        self.ui.set_page_header(input_page, "Known Values")
        self.ui.set_page_header(results_page, "Results")

        # Instructions
        instructions.add_elements([
            controls.Text(
                "<details><summary>Instructions (click to expand)</summary>"
                "<div style=\"padding-top:10px;\">"
                "<p>Structure Search finds a group of related values that stay at fixed offsets from each other.</p>"
                "<ol>"
                "<li>Select the target process.</li>"
                "<li>Load a Code List (.codes).</li>"
                "<li>Enter any known values (leave others blank).</li>"
                "<li>Click Search. Pressing Search again refines results using the current known values. Use Reset to start over.</li>"
                "<li>Review a single result with left/right. The header button applies that result to the Codes tab.</li>"
                "<li>Each value is editable; edits write directly to memory.</li>"
                "</ol>"
                "</div></details>"
            )
        ])

        # Process select
        ps_page.add_elements([
            controls.advanced.ProcessSelect(self._on_process_selected, id='CTRL_PROCESS')
        ])

        # File select
        row = controls.Row(id='ROW_FILE')
        row.add_element(controls.Text("Code List:", width="120px"))
        row.add_element(controls.Select([], self._on_file_changed, id='FILE_SELECT'))
        row.add_element(controls.Button("Refresh", self._on_refresh_files, id='FILE_REFRESH'))
        file_page.add_element(row)
        file_page.add_element(controls.Text("", id='FILE_STATUS'))

        # Input grid area (dynamic)
        input_page.add_element(controls.Group(id='GROUP_INPUTS'))
        # Inline results navigation + actions
        nav_row = controls.Row(id='RESULT_NAV_ROW')
        nav_row.add_element(controls.advanced.IconButton("md-chevron-left", self._on_nav_prev, id='BTN_RESULT_PREV'))
        nav_row.add_element(controls.Button("Use Result", self._on_use_current, id='BTN_RESULT_USE'))
        nav_row.add_element(controls.advanced.IconButton("md-chevron-right", self._on_nav_next, id='BTN_RESULT_NEXT'))
        nav_row.add_element(controls.Text("0/0", id='TXT_RESULT_INDEX'))
        input_page.add_element(nav_row)
        input_page.add_elements([
            controls.Button("Search", self._on_search, id='BTN_SEARCH'),
            controls.Button("Reset", self._on_reset, id='BTN_RESET'),
            controls.Text("", id='SEARCH_STATUS')
        ])

        # Results area
        results_group = StructureResultsGroup(on_use=self._on_use_result, on_prev=self._on_nav_prev, on_next=self._on_nav_next, on_edit=self._on_edit_value, id='GROUP_RESULTS')
        results_page.add_element(results_group)

    def on_ready(self):
        # Start with only instructions + process
        self.ui.get_element("PAGE_FILE").hide()
        self.ui.get_element("PAGE_INPUT").hide()
        self.ui.get_element("PAGE_RESULTS").hide()
        self._refresh_files()

    # --------------------------- UI handlers ---------------------------

    def _on_process_selected(self, proc):
        self.put_data("PROCESS", proc)
        if proc is None:
            self.ui.get_element("PAGE_FILE").hide()
            self.ui.get_element("PAGE_INPUT").hide()
            self.ui.get_element("PAGE_RESULTS").hide()
            return
        self.ui.get_element("PAGE_FILE").show()

    def _on_refresh_files(self, name: str, ele_id: str, data):
        self._refresh_files()

    def _refresh_files(self):
        files = self._get_code_files()
        self.put_data("FILES", files)
        sel = self.ui.get_element('FILE_SELECT')
        values = [('_null', '')] + [(f, f) for f in files]
        sel.set_values(values)
        self.ui.get_element('FILE_STATUS').set_text("Found {} code lists.".format(len(files)))

    def _on_file_changed(self, name: str, ele_id: str, data):
        # name: 'FILE_SELECT'
        selection = data.get('value') if isinstance(data, dict) else None
        if selection == '_null':
            self.put_data("SELECTED_FILE", "_null")
            self.put_data("CODES", [])
            self.ui.get_element("PAGE_INPUT").hide()
            self.ui.get_element("PAGE_RESULTS").hide()
            return
        self.put_data("SELECTED_FILE", selection)
        # Load file and build inputs
        try:
            codes = self._load_codes(selection)
            self.put_data("CODES", codes)
            self._build_inputs(codes)
            self.ui.get_element("PAGE_INPUT").show()
            self.ui.get_element("PAGE_RESULTS").hide()
            self.ui.get_element('SEARCH_STATUS').set_text("")
        except Exception as e:
            logger.exception("Failed to load codes")
            self.ui.get_element('FILE_STATUS').set_text("Could not load file: {}".format(selection))

    def _build_inputs(self, codes: List[Dict[str, Any]]):
        grp: controls.Group = self.ui.get_element('GROUP_INPUTS')
        # Clear old
        grp.inner('')

        # Header
        header = '<ons-row>' \
                 '<ons-col class="col ons-col-inner" width="10%"><b>Offset</b></ons-col>' \
                 '<ons-col class="col ons-col-inner" width="30%"><b>Name</b></ons-col>' \
                 '<ons-col class="col ons-col-inner" width="15%"><b>Type</b></ons-col>' \
                 '<ons-col class="col ons-col-inner" width="25%"><b>Known Value</b></ons-col>' \
                 '<ons-col class="col ons-col-inner" width="20%"><b>Result Value</b></ons-col>' \
                 '</ons-row>'
        body = ''
        for idx, code in enumerate(codes):
            name = code.get('Name', f'Code {idx}')
            tp = code.get('Type', 'byte_4')
            supported = tp in SupportedTypes
            input_id = f"KNOWN_{idx}"
            placeholder = '' if supported else '(unsupported)'
            readonly = 'readonly' if not supported else ''
            offset_display = str(code.get('__offset', 0)) if isinstance(code.get('__offset', 0), int) else str(code.get('__offset', 0))
            row = '<ons-row>' \
                    f'<ons-col class="col ons-col-inner" width="10%">{offset_display}</ons-col>' \
                    f'<ons-col class="col ons-col-inner" width="30%">{name}</ons-col>' \
                    f'<ons-col class="col ons-col-inner" width="15%">{tp.upper()}</ons-col>' \
                    f'<ons-col class="col ons-col-inner" width="25%">' \
                    f'<input type="text" id="{input_id}" class="text-input text-input--material text-full" {readonly} placeholder="{placeholder}" />' \
                    '</ons-col>' \
                    f'<ons-col class="col ons-col-inner" width="20%">' \
                    f'<input type="text" id="GROUP_INPUTS_RESULT_{idx}" data-key="{idx}" class="text-input text-input--material text-full" oninput="script.script_interact_value(event)" />' \
                    '</ons-col>' \
                    '</ons-row>'
            body += row
        grp.inner(header + body)

    def _on_search(self, name: str, ele_id: str, data):
        # Defer actual searching to frame() after collecting values from DOM via JS
        self.put_data("PENDING_SEARCH", True)
        # Collect values and send as JSON map index->value to avoid order issues
        collect_js = r"""
        (function(){
          var vals = {};
          var nodes = document.querySelectorAll('input[id^="KNOWN_"]');
          nodes.forEach(function(el){
            var m = el.id.match(/^KNOWN_(\d+)$/);
            if (m) { vals[m[1]] = el.value; }
          });
          var payload = JSON.stringify({ type: 'SCRIPT_INTERACT', id: 'KNOWN_COLLECT', data: { values: vals } });
          $.ajax({ url: '/script', type: 'POST', data: payload, dataType: 'json', contentType: 'application/json; charset=utf-8', success: function(r){} });
        })();
        """
        self.ui.js(collect_js)
        self.ui.get_element('SEARCH_STATUS').set_text("Collecting values...")

    def handle_interaction(self, _id, data):
        if _id == 'KNOWN_COLLECT':
            vals = None
            try:
                if isinstance(data, dict) and 'values' in data:
                    v = data['values']
                    if isinstance(v, list):
                        vals = v
                    elif isinstance(v, dict):
                        # normalize keys to ints when possible
                        vals = { (int(k) if str(k).isdigit() else k): v[k] for k in v }
                    else:
                        vals = []
                else:
                    vals = []
            except Exception:
                vals = []
            self.put_data('COLLECTED_VALUES', vals)
            return
        # Inline result value edits in the Known Values table
        if isinstance(_id, str) and _id.startswith('GROUP_INPUTS_RESULT_') and isinstance(data, dict) and data.get('type') == 'text':
            key = None
            try:
                if 'data' in data and 'key' in data['data']:
                    key = int(data['data']['key'])
            except Exception:
                key = None
            if key is not None:
                self._on_edit_value('', _id, {'index': self.get_data('RESULT_INDEX') or 0, 'key': key, 'value': data.get('value')})
            return
        return super().handle_interaction(_id, data)

    def frame(self):
        # If a search is pending and values were collected, perform the search
        if self.get_data('PENDING_SEARCH') and self.get_data('COLLECTED_VALUES') is not None:
            self.ui.get_element('SEARCH_STATUS').set_text("Searching...")
            try:
                codes = self.get_data("CODES") or []
                raw_vals = self.get_data('COLLECTED_VALUES') or []
                known = {}
                for idx, code in enumerate(codes):
                    tp = code.get('Type', 'byte_4')
                    if tp not in SupportedTypes:
                        continue
                    txt = ''
                    if isinstance(raw_vals, dict):
                        val = raw_vals.get(idx) if idx in raw_vals else raw_vals.get(str(idx)) if isinstance(raw_vals, dict) else None
                        if val is not None:
                            txt = str(val).strip()
                    else:
                        if idx < len(raw_vals) and raw_vals[idx] is not None:
                            txt = str(raw_vals[idx]).strip()
                    if not txt:
                        continue
                    try:
                        val = self._parse_value(txt, tp, code.get('Signed', False))
                    except Exception:
                        continue
                    known[idx] = val

                if not known:
                    self.ui.get_element('SEARCH_STATUS').set_text("Enter at least one known value.")
                    self.put_data('PENDING_SEARCH', False)
                    self.put_data('COLLECTED_VALUES', None)
                    return

                resolved, offsets, anchor_index = self._prepare_structure(codes, known)
                if anchor_index < 0:
                    self.ui.get_element('SEARCH_STATUS').set_text("Could not resolve an anchor field.")
                    self.put_data('PENDING_SEARCH', False)
                    self.put_data('COLLECTED_VALUES', None)
                    return

                # If we have prior results, refine within them; otherwise run full anchor search (with progress)
                prior_rows = self.get_data('RESULT_ROWS') or []
                candidates_override = None
                skip_anchor_check = False
                # Define anchor props for initial search/progress
                try:
                    anchor_type = codes[anchor_index].get('Type', 'byte_4')
                    anchor_signed = bool(codes[anchor_index].get('Signed', False))
                    anchor_value = known[anchor_index]
                except Exception:
                    anchor_type, anchor_signed, anchor_value = 'byte_4', False, 0
                if prior_rows:
                    # Prefer previous row addresses for the new anchor index to avoid drift
                    cand_from_rows = []
                    for r in prior_rows:
                        addrs = r.get('addresses', [])
                        try:
                            a = addrs[anchor_index]
                        except Exception:
                            a = None
                        if a is not None and int(a) > 0:
                            cand_from_rows.append(int(a))
                    if cand_from_rows:
                        candidates_override = cand_from_rows
                        skip_anchor_check = False
                    elif offsets[anchor_index] is not None:
                        # Fallback to base + offset
                        candidates_override = [r.get('base', 0) + int(offsets[anchor_index]) for r in prior_rows if 'base' in r]
                        skip_anchor_check = False
                    else:
                        candidates_override = None
                        skip_anchor_check = True
                else:
                    # Simple synchronous search without progress reporting
                    candidates_override = None
                    skip_anchor_check = True

                results = self._search_by_offsets(codes, known, resolved, offsets, anchor_index, candidates_override=candidates_override, skip_anchor_check=skip_anchor_check)
                # Clear any stale scan state (progress removed)
                self.put_data('SCAN_ACTIVE', False)
                self.put_data('SCAN_CANDIDATES', [])
                self.put_data('SCAN_LAST_DONE', -1)
                self.put_data('SCAN_STALL_COUNT', 0)

                headers = [{
                    'name': c.get('Name', f'Code {i}'),
                    'type': c.get('Type', 'byte_4')
                } for i, c in enumerate(codes)]
                # Store and show first result inline next to Known Values
                self.put_data("RESULT_ROWS", results)
                self.put_data('RESULT_INDEX', 0)
                self._render_single_result(0)
                # Update nav label and buttons
                total = len(results)
                self.ui.get_element('TXT_RESULT_INDEX').set_text('{}/{}'.format(1 if total else 0, total))
                if total <= 1:
                    self.ui.get_element('BTN_RESULT_PREV').disable()
                    self.ui.get_element('BTN_RESULT_NEXT').disable()
                else:
                    self.ui.get_element('BTN_RESULT_PREV').disable()
                    self.ui.get_element('BTN_RESULT_NEXT').enable()
                self.ui.get_element('SEARCH_STATUS').set_text("Found {} matches.".format(total))
            except Exception as e:
                logger.exception("Search failed")
                self.ui.get_element('SEARCH_STATUS').set_text("Search failed: {}".format(str(e)))
            finally:
                self.put_data('PENDING_SEARCH', False)
                self.put_data('COLLECTED_VALUES', None)

    def _on_use_result(self, _gid: str, _btn_id: str, data: dict):
        row = data.get('row', {}) if data else {}
        addresses = row.get('addresses', [])
        filename = self.get_data("SELECTED_FILE") or '_null'
        if filename == '_null' or not addresses:
            return

        # Emit JS to load file and set each code to address source with new address
        # 1) Load the file into the Codes tab service
        js = "$.send('/codelist', { 'command': 'CODELIST_LOAD', 'file': '" + filename + "' }, function(r){});"
        self.ui.js(js)

        # 2) For each code entry, update as address
        # Map sorted index -> original file index stored with each code
        current_codes = self.get_data('CODES') or []
        for idx, addr in enumerate(addresses):
            if addr is None or addr <= 0:
                continue
            addr_hex = "{:X}".format(int(addr))
            try:
                file_index = current_codes[idx].get('__file_index', idx)
            except Exception:
                file_index = idx
            cmd = {
                'command': 'CODELIST_ADD_CODE',
                'type': 'address',
                'index': file_index,
                'address': addr_hex
            }
            cmd_js = "$.send('/codelist', {} , function(r){{}});".format(json.dumps(cmd))
            self.ui.js(cmd_js)

        # Notify and switch to Codes tab to trigger UI refresh
        self.ui.js("ons.notification.toast('Applied structure addresses to Codes.', { timeout: 2000 });")
        self.ui.js("var tb=document.querySelector('ons-tabbar'); if(tb){tb.setActiveTab(0);} ")
        self.ui.js("setTimeout(function(){ var sel=document.getElementById('codelist_file_selection'); if(sel){ sel.value=" + json.dumps(filename) + "; var ev=new Event('change'); sel.dispatchEvent(ev);} }, 300);")

    def _on_use_top(self, name: str, ele_id: str, data):
        rows = self.get_data('RESULT_ROWS') or []
        if not rows:
            return
        self._on_use_result('', '', {'row': rows[0]})

    def _on_nav_prev(self, name: str, ele_id: str, data: dict):
        rows = self.get_data('RESULT_ROWS') or []
        if not rows:
            return
        idx = max(0, (self.get_data('RESULT_INDEX') or 0) - 1)
        self.put_data('RESULT_INDEX', idx)
        self._render_single_result(idx)

    def _on_nav_next(self, name: str, ele_id: str, data: dict):
        rows = self.get_data('RESULT_ROWS') or []
        if not rows:
            return
        idx = min(len(rows)-1, (self.get_data('RESULT_INDEX') or 0) + 1)
        self.put_data('RESULT_INDEX', idx)
        self._render_single_result(idx)

    def _on_use_current(self, name: str, ele_id: str, data: dict):
        rows = self.get_data('RESULT_ROWS') or []
        if not rows:
            return
        idx = self.get_data('RESULT_INDEX') or 0
        if idx < 0 or idx >= len(rows):
            return
        self._on_use_result('', '', {'row': rows[idx]})

    def _on_edit_value(self, _gid: str, _id: str, data: dict):
        try:
            idx = int(data.get('index')) if 'index' in data else (self.get_data('RESULT_INDEX') or 0)
        except Exception:
            idx = self.get_data('RESULT_INDEX') or 0
        key = data.get('key')
        txt = data.get('value')
        rows = self.get_data('RESULT_ROWS') or []
        codes = self.get_data('CODES') or []
        if rows and codes and key is not None:
            try:
                key = int(key)
                addr = rows[idx]['addresses'][key]
                if addr is None or addr <= 0:
                    return
                code = codes[key]
                tp = code.get('Type', 'byte_4')
                signed = bool(code.get('Signed', False))
                if tp == 'float':
                    val = float(txt)
                    self.get_memory().write_memory(int(addr), ctypes.c_float(val))
                else:
                    ival = int(txt, 16) if str(txt).lower().startswith('0x') else int(txt)
                    ctp = self._ctype_for_code(code)
                    self.get_memory().write_memory(int(addr), ctp(ival))
            except Exception:
                pass

    def _render_single_result(self, index: int):
        # Populate the inline result value column inputs for the specified result index
        rows = self.get_data('RESULT_ROWS') or []
        codes = self.get_data('CODES') or []
        total = len(rows)
        if not rows or not codes or index < 0 or index >= total:
            # Clear labels and inputs when no results
            self.ui.get_element('TXT_RESULT_INDEX').set_text('0/0')
            for i in range(len(codes)):
                input_id = 'GROUP_INPUTS_RESULT_{}'.format(i)
                self.ui.js("$('#'+{}).val('');".format(json.dumps(input_id)))
            return
        row = rows[index]
        # Update header label and nav button states
        self.ui.get_element('TXT_RESULT_INDEX').set_text('{}/{}'.format(index+1, total))
        if index <= 0:
            self.ui.get_element('BTN_RESULT_PREV').disable()
        else:
            self.ui.get_element('BTN_RESULT_PREV').enable()
        if index >= total-1:
            self.ui.get_element('BTN_RESULT_NEXT').disable()
        else:
            self.ui.get_element('BTN_RESULT_NEXT').enable()
        # Fill per-code result value inputs
        for i, code in enumerate(codes):
            try:
                addr = row['addresses'][i]
            except Exception:
                addr = None
            if addr is None or addr <= 0:
                val_str = ''
            else:
                v = self._read_value(addr, code)
                if v is None:
                    val_str = ''
                else:
                    if code.get('Type', 'byte_4') == 'float':
                        try:
                            val_str = '{:.6f}'.format(float(v))
                        except Exception:
                            val_str = str(v)
                    else:
                        try:
                            val_str = str(int(v))
                        except Exception:
                            val_str = str(v)
            input_id = 'GROUP_INPUTS_RESULT_{}'.format(i)
            self.ui.js("$('#'+{}).val({});".format(json.dumps(input_id), json.dumps(val_str)))

    def _on_reset(self, name: str, ele_id: str, data):
        # Clear prior results so the next Search is full-memory (not refined)
        self.put_data('RESULT_ROWS', [])
        self.ui.get_element('PAGE_RESULTS').hide()
        self.ui.get_element('SEARCH_STATUS').set_text("Reset. Ready for a new search.")

    def _start_anchor_scan(self, codes: List[Dict[str, Any]], known: Dict[int, Any], anchor_index: int):
        # Prepare async scan state
        self.put_data('SCAN_ACTIVE', True)
        self.put_data('SCAN_DONE', 0)
        self.put_data('SCAN_TOTAL', 0)
        self.put_data('SCAN_CANDIDATES', [])
        try:
            anchor_type = codes[anchor_index].get('Type', 'byte_4')
            anchor_signed = bool(codes[anchor_index].get('Signed', False))
            anchor_value = known[anchor_index]
        except Exception:
            self.put_data('SCAN_ACTIVE', False)
            return

        import threading
        t = threading.Thread(target=self._scan_worker, args=(anchor_type, anchor_signed, anchor_value), daemon=True)
        self.put_data('SCAN_THREAD', t)
        t.start()

    def _scan_worker(self, anchor_type: str, anchor_signed: bool, anchor_value):
        # Build value object
        try:
            sv = Value.create(str(anchor_value), anchor_type, anchor_signed)
        except Exception:
            self.put_data('SCAN_ACTIVE', False)
            return
        # Regions and totals
        searcher = self.get_memory_manager().get_searcher('structure_scan')
        total = 0
        for start, stop in searcher.get_regions():
            total += (stop - start)
        self.put_data('SCAN_TOTAL', int(total))
        done = 0
        candidates = []
        chunk_size = 8 * 1024 * 1024  # 8MB
        from app.search.buffer import SearchBuffer
        for start, stop in searcher.get_regions():
            i_start = start
            while i_start < stop:
                try:
                    size = min(stop - i_start, chunk_size)
                    if size <= 0:
                        break
                    region_buffer = (ctypes.c_byte * size)()
                    self.get_memory().read_memory(i_start, region_buffer)
                    sb = SearchBuffer.create(region_buffer, i_start, sv, aligned=True)
                    processed = sb.find_value(sv)
                    # Collect addresses
                    for addr, _ in sb.results:
                        try:
                            candidates.append(int(addr))
                        except Exception:
                            continue
                    done += processed
                    self.put_data('SCAN_DONE', int(min(done, total)))
                    # Update UI from worker thread is safe (queues updates)
                    remaining = max(0, total - done)
                    self.ui.get_element('SEARCH_STATUS').set_text("Searching... remaining {} bytes".format(remaining))
                    i_start += size
                except OSError:
                    # unreadable, skip chunk
                    i_start += chunk_size
                    done += chunk_size
                    self.put_data('SCAN_DONE', int(min(done, total)))
                except Exception:
                    i_start += chunk_size
                    done += chunk_size
                    self.put_data('SCAN_DONE', int(min(done, total)))
        self.put_data('SCAN_CANDIDATES', candidates)
        self.put_data('SCAN_DONE', int(total))

    # --------------------------- Helpers ---------------------------

    def _get_code_files(self) -> List[str]:
        try:
            pts = list(codes_directory.glob('*.codes'))
            items = [(p.stem, p.stat().st_mtime) for p in pts]
            return [x[0] for x in sorted(items, key=lambda y: y[1])]
        except Exception:
            return []

    def _load_codes(self, filename: str) -> List[Dict[str, Any]]:
        pt = codes_directory.joinpath(filename + '.codes')
        data = json.loads(pt.read_text())
        codes_raw = data.get('codes', data if isinstance(data, list) else [])
        # normalize + filter: only Source=='address' and supported Type
        codes: List[Dict[str, Any]] = []
        for i, c in enumerate(codes_raw):
            c.setdefault('Name', f'Code {i}')
            c.setdefault('Type', 'byte_4')
            c.setdefault('Signed', False)
            c.setdefault('Source', 'address')
            c['__file_index'] = i
            # filter out non-address sources and unsupported types
            if c.get('Source', 'address') != 'address':
                continue
            if c.get('Type') not in SupportedTypes:
                continue
            codes.append(c)
        # sort by resolved address ascending (unknowns last)
        def _addr_for_sort(cd):
            try:
                a = self._resolve_code_address(cd)
                if a is None or a <= 0:
                    return 1 << 62
                return int(a)
            except Exception:
                return 1 << 62
        codes_sorted = sorted(codes, key=_addr_for_sort)
        # compute offsets relative to first resolved address
        base_addr = None
        for cd in codes_sorted:
            a = self._resolve_code_address(cd)
            if a is not None and a > 0:
                base_addr = int(a)
                break
        for cd in codes_sorted:
            a = self._resolve_code_address(cd)
            if base_addr is not None and a is not None and a > 0:
                cd['__offset'] = int(a) - base_addr
            else:
                cd['__offset'] = '-'  # unknown
        return codes_sorted

    def _parse_value(self, txt: str, tp: str, signed: bool):
        if tp == 'float':
            return float(txt)
        # integer types
        if txt.lower().startswith('0x'):
            iv = int(txt, 16)
        else:
            iv = int(txt, 10)
        # Limit/convert via ctype for compare type
        ctp = get_ctype(str(iv), tp)
        val = ctp(iv)
        return val.value

    def _resolve_code_address(self, code: Dict[str, Any]) -> Optional[int]:
        # Resolve absolute address per code entry for current process
        src = code.get('Source', 'address')
        try:
            if src == 'address':
                addr_str = code.get('Address', '')
                if not addr_str:
                    return None
                return self.get_memory_manager().get_address(addr_str if ':' in addr_str or address_match(addr_str) else addr_str.upper())
            # Explicitly exclude pointer and AOB entries for structure search
            return None
        except Exception:
            return None

    def _prepare_structure(self, codes: List[Dict[str, Any]], known: Dict[int, Any]) -> Tuple[List[Optional[int]], List[Optional[int]], int]:
        # Resolve addresses for as many codes as possible (for offset derivation)
        resolved: List[Optional[int]] = [self._resolve_code_address(c) for c in codes]
        # choose anchor: first index in known with resolved address
        anchor_index = -1
        for idx in sorted(known.keys()):
            if resolved[idx] is not None and resolved[idx] > 0:
                anchor_index = idx
                break
        if anchor_index < 0:
            return resolved, [], -1
        anchor_addr = int(resolved[anchor_index])
        offsets: List[Optional[int]] = []
        for i, addr in enumerate(resolved):
            if addr is None or addr <= 0:
                offsets.append(None)
            else:
                offsets.append(int(addr) - anchor_addr)
        self.put_data("OFFSETS", offsets)
        self.put_data("ANCHOR_INDEX", anchor_index)
        return resolved, offsets, anchor_index

    def _search_by_offsets(self, codes: List[Dict[str, Any]], known: Dict[int, Any], resolved: List[Optional[int]], offsets: List[Optional[int]], anchor_index: int, candidates_override: Optional[List[int]] = None, skip_anchor_check: bool = False):
        # Use anchor value and type to perform primary search
        anchor_type = codes[anchor_index].get('Type', 'byte_4')
        anchor_signed = codes[anchor_index].get('Signed', False)
        anchor_value = known[anchor_index]

        # Determine candidate anchor addresses
        if candidates_override is not None:
            candidates: List[int] = list(candidates_override)
        else:
            searcher = self.get_memory_manager().get_searcher('structure_search')
            searcher.reset()
            searcher.set_search_size(anchor_type)
            searcher.set_signed(anchor_signed)
            # Convert value into search string via Value.create representation
            val_str = str(anchor_value)
            if isinstance(anchor_value, float):
                val_str = str(anchor_value)
            # perform search
            searcher.search_memory_value(val_str)

            # Gather candidates (scan all results; chunked to avoid large memory use)
            candidates = []
            with searcher.results.db() as conn:
                try:
                    total = searcher.results.get_number_of_results(conn, -1)
                except Exception:
                    total = 0
                chunk = 20000
                offset = 0
                while offset < total:
                    count = min(chunk, total - offset)
                    cur = searcher.results.get_results(conn, _offset=offset, _count=count)
                    rows = cur.fetchall()
                    for row in rows:
                        candidates.append(int(row[0]))
                    offset += count

        # Validate candidates against all filled known values
        rows: List[Dict[str, Any]] = []
        for cand_addr in candidates:
            base0 = cand_addr - offsets[anchor_index]
            if base0 <= 0:
                continue
            ok = True
            for idx, val in known.items():
                # Skip the anchor index only when candidates were built from an anchor search
                if skip_anchor_check and idx == anchor_index:
                    continue
                # Only validate against entries with known offsets
                if offsets[idx] is None:
                    continue
                off = offsets[idx]
                addr = base0 + off
                if not self._compare_at_address(addr, codes[idx]):
                    ok = False
                    break
                # Compare precise value
                cv = self._read_value(addr, codes[idx])
                if isinstance(val, float):
                    if cv is None:
                        ok = False
                        break
                    try:
                        fcv = float(cv)
                    except Exception:
                        ok = False
                        break
                    if math.isnan(fcv):
                        ok = False
                        break
                    # Match tolerance for float equality (~0.001)
                    if abs(fcv - float(val)) > 0.001:
                        ok = False
                        break
                else:
                    if cv is None or int(cv) != int(val):
                        ok = False
                        break
            if not ok:
                continue
            # Build row addresses for all codes
            row_addrs: List[Optional[int]] = []
            for i, _ in enumerate(codes):
                if offsets[i] is None:
                    row_addrs.append(None)
                else:
                    row_addrs.append(base0 + offsets[i])
            rows.append({'base': base0, 'addresses': row_addrs})
            if len(rows) >= 200:
                break
        return rows

    def _ctype_for_code(self, code: Dict[str, Any]):
        tp = code.get('Type', 'byte_4')
        signed = bool(code.get('Signed', False))
        if tp == 'float':
            return ctypes.c_float
        # map sizes
        if tp == 'byte_1':
            return ctypes.c_int8 if signed else ctypes.c_uint8
        if tp == 'byte_2':
            return ctypes.c_int16 if signed else ctypes.c_uint16
        if tp == 'byte_4':
            return ctypes.c_int32 if signed else ctypes.c_uint32
        if tp == 'byte_8':
            return ctypes.c_int64 if signed else ctypes.c_uint64
        return None

    def _read_value(self, addr: int, code: Dict[str, Any]):
        ctp = self._ctype_for_code(code)
        if ctp is None:
            return None
        try:
            v = self.get_memory().read_memory(int(addr), ctp())
            return v.value
        except Exception:
            return None

    def _compare_at_address(self, addr: int, code: Dict[str, Any]) -> bool:
        # Check we can read the given type at address
        return self._read_value(addr, code) is not None

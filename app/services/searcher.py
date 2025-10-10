import copy
import ctypes
import json
import logging
import math
import traceback
import uuid
from queue import PriorityQueue
from threading import Thread, Lock
from typing import Union

from falcon import Request, Response
from falcon.app_helpers import MEDIA_JSON

from app.helpers import DataStore, DynamicHTML, MemoryHandler, Progress
from app.helpers import memory_utils
from app.helpers.exceptions import SearchException, BreakException, CodelistException
from app.helpers.search_results import SearchResults
from app.search.operations import GreaterThan, LessThan, GreaterThanFloat, LessThanFloat, IncreaseOperation, \
    DecreaseOperation, \
    IncreaseOperationFloat, DecreaseOperationFloat, ChangedOperation, UnchangedOperation, ChangedOperationFloat, \
    UnchangedOperationFloat, ChangedByOperation, ChangedByOperationFloat
from app.search.searcher import Searcher
from app.search.searcher_multi import SearcherMulti
from app.search.value import Value
from app.helpers.directory_utils import memory_directory
from app.helpers.process import BaseConvert, BaseConvertException
from app.services.codes import CodeList

ctypes_buffer_t = Union[ctypes._SimpleCData, ctypes.Array, ctypes.Structure, ctypes.Union]


class Search(MemoryHandler):
    FLOW_START = 4
    FLOW_SEARCHING = 6
    FLOW_RESULTS = 0
    FLOW_NO_RESULTS = 2
    FLOW_INITIALIZE_UNKNOWN = 1
    def __init__(self):
        super().__init__('search')
        self.handle_map = {
            "SEARCH_INITIALIZE": self.handle_initialization,
            "SEARCH_RESULT_UPDATE": self.handle_result_update,
            "SEARCH_RESET": self.handle_reset,
            "SEARCH_START": self.handle_search,
            "SEARCH_STATUS": self.handle_initialization,
            "SEARCH_WRITE": self.handle_write,
            "SEARCH_FREEZE": self.handle_freeze,
            "SEARCH_STRUCTURE_GROUPS": self.handle_structure_groups,
            "SEARCH_STRUCTURE_RUN": self.handle_structure_run,
            "SEARCH_STRUCTURE_APPLY": self.handle_structure_apply,
        }
        self.search_map = {
            'equal_to': self._equal_search,
            'greater_than': self._greater_search,
            'less_than': self._lesser_search,
            'unknown': self._unknown_search,
            'unknown_near': self._unknown_near_search,
            'increase': self._increase_search,
            'decrease': self._decrease_search,
            'changed': self._changed_search,
            'unchanged': self._unchanged_search,
            'changed_by': self._changed_by_search
        }
        self.flow = self.FLOW_START
        self.type = ""
        self.size = ""
        self.proximity = {}
        self.aligned = True
        self.value: Value = None
        self.searcher: SearcherMulti = None


        self.search_thread: Thread = None
        self.update_thread: Search.UpdateThread = None

        self.previous_stats = {'results': [], 'flow': self.FLOW_START, 'round': 0}
        self.round = 0
        self.progress = Progress()

    def kill(self):
        if self.search_thread and self.search_thread.is_alive():
            self.searcher.cancel()
            self.search_thread.join()
        self.stop_updater()


    def release(self):
        self.reset()

    def process_error(self, msg: str):
        self.reset()

    def set(self, data):
        self.round = 0
        if self.searcher:
            self.searcher.set_memory(self.mem())
            self.searcher.reset()
        pass


    def html_main(self):
        return DynamicHTML('resources/search.html', 1).get_html()

    def reset(self):
        if self.search_thread and self.search_thread.is_alive():
            self.searcher.cancel()
            self.search_thread.join()
        self.progress.reset()
        self.stop_updater()
        self.searcher.reset()
        self.round = 0
        self.type = ""
        self.size = ""
        self.proximity = {}
        self.aligned = True
        self.value = None
        self.search_thread: Thread = None
        self.update_thread: Search.UpdateThread = None
        self.previous_stats = {'results': [], 'flow': self.FLOW_START, 'round': 0}
        self.flow = self.FLOW_START



    def handle_initialization(self, req: Request, resp: Response):
        if self.flow == self.FLOW_START:
            if self.type:
                resp.media['type'] = self.type
            if self.size:
                resp.media['size'] = self.size
            if self.value:
                resp.media['value'] = str(self.value.get_printable())
        elif self.flow == self.FLOW_SEARCHING:
            resp.media['progress'] = self.progress.get_progress() if self.progress else 0
            resp.media['repeat'] = 1000
            resp.media['round'] = self.round
            resp.media['results'] = []
            resp.media['count'] = 0
            resp.media['type'] = self.type
            resp.media['size'] = self.size
            resp.media['value'] = str(self.value.get_printable())
        elif self.flow == self.FLOW_RESULTS:
            resp.media['round'] = self.round
            resp.media['results'] = self.get_updated_addresses()
            resp.media['type'] = self.type
            resp.media['size'] = self.size
            resp.media['value'] = str(self.value.get_printable()) if self.is_value_search() else "0"
            resp.media['count'] = len(self.searcher.results)
            resp.media['repeat'] = 0


    def handle_reset(self, req: Request, resp: Response):
        if self.flow == self.FLOW_SEARCHING: #we are stopping
            self.searcher.cancel()
            self.search_thread.join()
            self.progress.reset()
            if not self.searcher.get_cancel(): #was cancellation successful:
                self.round = self.previous_stats['round']
                self.flow = self.previous_stats['flow']
                resp.media['results'] = self.get_updated_addresses()
                resp.media['round'] = self.round
                resp.media['type'] = self.type
                resp.media['size'] = self.size
                resp.media['value'] = str(self.value.get())
                resp.media['count'] = len(self.searcher.results)
                if self.flow == self.FLOW_RESULTS:
                    self.stop_updater()
                    self.start_updater()
        else:
            if self.type in ['increase', 'decrease', 'unchanged', 'changed', 'changed_by']:
                self.type = 'equal_to'
            self.progress.reset()
            self.stop_updater()
            self.proximity = {}
            self.flow = self.FLOW_START
            resp.media['results'] = []
            self.round = 0
            self.value = None
            self.size = 'byte_4'
            resp.media['round'] = self.round
            resp.media['type'] = self.type
            resp.media['size'] = self.size
            resp.media['value'] = ""
            resp.media['count'] = 0
            resp.media['proximity'] = self.proximity
            self.reset()

    def handle_search(self, req: Request, resp: Response):
        if self.search_thread and self.search_thread.is_alive():
            self.memory.break_search()
            self.search_thread.join()
        self.stop_updater()
        self.type = req.media['type']
        self.size = req.media['size']
        self.proximity = json.loads(req.media['proximity'])
        sv = req.media['value'] if self.is_value_search() and len(req.media['value']) > 0 else "0"
        self.value = Value.create(sv, req.media['size'])
        resp.media['type'] = self.type
        resp.media['size'] = self.size
        resp.media['value'] = self.value.get_printable()
        if req.media['type'] not in self.search_map:
            if self.round == 0:
                self.flow = self.FLOW_START
            raise SearchException("Search type {} is not valid".format(req.media['type']))
        if not self.searcher:
            self.searcher = SearcherMulti(self.mem(), self.progress)
            self.searcher.reset()
        if (self.flow == self.FLOW_START and self.size == 'float') or \
                (self.flow == self.FLOW_INITIALIZE_UNKNOWN and self.size != 'byte_1') or \
                (self.flow == self.FLOW_START and (self.type == 'greater_than' or self.type == 'less_than') and self.size != 'byte_1'):
            self.aligned = req.media['aligned'] == 'true'
        else:
            self.aligned = True
        search_op = self.search_map[req.media['type']]
        self.search_thread = Thread(target=self._search, args=[search_op])
        self.previous_stats['flow'] = self.flow
        self.previous_stats['round'] = self.round
        self.previous_stats['results'] = None
        self.flow = self.FLOW_SEARCHING
        resp.media['progress'] = 0
        resp.media['repeat'] = 400
        resp.media['round'] = 0
        resp.media['results'] = []
        resp.media['count'] = 0
        self.search_thread.start()

    def handle_write(self, req: Request, resp: Response):
        if not self.update_thread or not self.update_thread.is_alive():
            raise SearchException("Update thread not running. Can't write value.")
        try:
            addr = int(req.media['address'])
            value = Value.create(req.media['value'], self.value.get_store_type())
            self.update_thread.write(addr, value)
        except Exception:
            raise SearchException("Address or value is not valid for write.")
        finally:
            resp.media['round'] = self.round
            resp.media['results'] = self.get_updated_addresses()
            resp.media['count'] = len(self.searcher.results)
            resp.media['type'] = self.type
            resp.media['size'] = self.size
            resp.media['value'] = str(self.value.get())


    def handle_freeze(self, req: Request, resp: Response):
        if not self.update_thread or not self.update_thread.is_alive():
            raise SearchException("Update thread not running. Can't freeze value.")
        try:
            addr = int(req.media['address'])
            tp = memory_utils.typeToCType[(self.size, False)]
            if self.size == 'array':
                tp = (tp * memory_utils.aob_size(self.value.get_printable(), wildcard=True))
            val = self.mem().read_memory(addr, tp())
            freeze = req.media['freeze'] == 'true'
            self.update_thread.freeze(addr, val, freeze)
        except Exception:
            traceback.print_exc()
            raise SearchException("Address or value is not valid for write.")
        finally:
            resp.media['round'] = self.round
            resp.media['results'] = self.get_updated_addresses()
            resp.media['count'] = len(self.searcher.results)
            resp.media['type'] = self.type
            resp.media['size'] = self.size
            resp.media['value'] = str(self.value.get())

    def handle_result_update(self, req: Request, resp: Response):
        if not self.update_thread or not self.update_thread.is_alive():
            resp.media['repeat'] = 0
            resp.media['array'] = False
            resp.media['count'] = 0
            resp.media['results'] = []
        else:
            self.update_thread.add_action('refresh')
            resp.media['results'] = self.get_updated_addresses()
            resp.media['array'] = isinstance(self.update_thread.parsed_value, ctypes.Array)
            resp.media['count'] = len(self.searcher.results)
            resp.media['repeat'] = 1000

    def get_updated_addresses(self):
        if not self.update_thread:
            res = self.searcher.get_results(limit=40)
            Search.UpdateThread.results_to_update(self.size, res)
            return res
        return self.update_thread.get_addresses()


    def process(self, req: Request, resp: Response):
        resp.media = {}
        command = req.media['command']
        assert (command in self.handle_map)
        resp.content_type = MEDIA_JSON
        try:
            self.handle_map[command](req, resp)
        except SearchException as e:
            resp.media['error'] = e.get_message()
        finally:
            resp.media['flow'] = self.flow


    def _search(self, searcher):
        self.stop_updater()
        try:
            if self.proximity and self.proximity['enabled']:
                self.searcher.set_proximity(self.proximity['address'], int(self.proximity['size']))
            else:
                self.searcher.clear_proximity()
            self.searcher.set_aligned(self.aligned)
            searcher(copy.deepcopy(self.value))
        except BreakException:
            return
        except SearchException:
            self._search_error()
            return
        self._search_complete()

    def _search_complete(self):
        self.round += 1
        if self.searcher.has_results():
            if len(self.searcher.results) > 0:
                self.start_updater()
                self.flow = self.FLOW_RESULTS
            else:
                self.stop_updater()
                self.flow = self.FLOW_NO_RESULTS
        elif self.searcher.has_captures():
            self.flow = self.FLOW_INITIALIZE_UNKNOWN
        else:
            self.flow = self.FLOW_NO_RESULTS

    def _search_error(self):
        self.round += 1
        self.flow = self.FLOW_NO_RESULTS


    def _equal_search(self, value: Value):
        self.searcher.setup_by_value(value)
        if self.searcher.has_results():
            self.searcher.search_continue_value(str(value.get()))
        else:
            self.searcher.search_memory_value(str(value.get()))

    def _greater_search(self, value: Value):
        self.searcher.setup_by_value(value)
        if value.get_store_type() == 'float':
            op = GreaterThanFloat(value.get())
        else:
            op = GreaterThan(value.get())
        if self.searcher.has_results():
            self.searcher.search_continue_operation(op)
        else:
            self.searcher.search_memory_operation(op)

    def _lesser_search(self, value: Value):
        self.searcher.setup_by_value(value)
        if value.get_store_type() == 'float':
            op = LessThanFloat(value.get())
        else:
            op = LessThan(value.get())
        if self.searcher.has_results():
            self.searcher.search_continue_operation(op)
        else:
            self.searcher.search_memory_operation(op)

    def _unknown_search(self, value: Value):
        self.searcher.setup_by_value(value)
        self.searcher.capture_memory()

    def _unknown_near_search(self, value: Value):
        self.searcher.setup_by_value(value)
        self.searcher.capture_memory_range(value.get(), 0x100000)

    def _increase_search(self, value: Value):
        self.searcher.setup_by_value(value)
        if value.get_store_type() == 'float':
            op = IncreaseOperationFloat()
        else:
            op = IncreaseOperation()
        if self.searcher.has_results() or self.searcher.has_captures():
            self.searcher.search_continue_operation(op)
        else:
            self.searcher.search_memory_operation(op)

    def _decrease_search(self, value: Value):
        self.searcher.setup_by_value(value)
        if value.get_store_type() == 'float':
            op = DecreaseOperationFloat()
        else:
            op = DecreaseOperation()
        if self.searcher.has_results() or self.searcher.has_captures():
            self.searcher.search_continue_operation(op)
        else:
            self.searcher.search_memory_operation(op)

    def _changed_search(self, value: Value):
        self.searcher.setup_by_value(value)
        if value.get_store_type() == 'float':
            op = ChangedOperationFloat()
        elif value.get_store_type() == 'array':
            op = ChangedOperation()
        else:
            op = ChangedOperation()
        if self.searcher.has_results() or self.searcher.has_captures():
            self.searcher.search_continue_operation(op)
        else:
            raise SearchException("Invalid search")

    def _unchanged_search(self, value: Value):
        self.searcher.setup_by_value(value)
        if value.get_store_type() == 'float':
            op = UnchangedOperationFloat()
        elif value.get_store_type() == 'array':
            op = UnchangedOperation()
        else:
            op = UnchangedOperation()
        if self.searcher.has_results() or self.searcher.has_captures():
            self.searcher.search_continue_operation(op)
        else:
            raise SearchException("Invalid search")

    def _changed_by_search(self, value: Value):
        self.searcher.setup_by_value(value)
        if value.get_store_type() == 'float':
            op = ChangedByOperationFloat(value.get())
        else:
            op = ChangedByOperation(value.get())
        if self.searcher.has_results() or self.searcher.has_captures():
            self.searcher.search_continue_operation(op)
        else:
            raise SearchException("Invalid search")

    def is_done(self):
        if self.search_thread and self.search_thread.is_alive():
            return False
        return True

    def is_value_search(self):
        if self.type == 'equal_to' or self.type == 'greater_than' or self.type == 'less_than' or self.type == 'changed_by':
            return True
        return False

    def start_updater(self):
        self.stop_updater()
        self.update_thread = Search.UpdateThread(self.mem(), self.searcher.get_results(40), copy.deepcopy(self.value), self.searcher)
        self.update_thread.start()

    def stop_updater(self):
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.add_action('quit')
            self.update_thread.join()
        self.update_thread = None

    def handle_structure_groups(self, req: Request, resp: Response):
        file_name = (req.media.get('file') or "").strip()
        if not file_name:
            raise SearchException("Code list name is required")
        groups = self._load_structure_groups(file_name)
        resp.media['file'] = file_name
        resp.media['groups'] = []
        for entry in sorted(groups.values(), key=lambda grp: grp['name']):
            resp.media['groups'].append({
                'name': entry['name'],
                'base_index': entry['base']['index'],
                'base_address': '{:X}'.format(entry['base']['address']),
                'items': [
                    {
                        'index': item['index'],
                        'name': item['name'],
                        'type': item['type'],
                        'signed': item['signed'],
                        'address': '{:X}'.format(item['address']),
                        'offset': item['offset'],
                    }
                    for item in entry['items']
                ]
            })

    def handle_structure_run(self, req: Request, resp: Response):
        if not self.has_mem():
            raise SearchException("Attach to a process before running a structure search")
        file_name = (req.media.get('file') or "").strip()
        group_name = (req.media.get('group') or "").strip()
        if not file_name or not group_name:
            raise SearchException("Both code list and group are required")
        groups = self._load_structure_groups(file_name)
        group_key = group_name.casefold()
        if group_key not in groups:
            raise SearchException("Selected rebase group was not found in the code list")
        group_entry = groups[group_key]
        base_item = group_entry['base']
        try:
            base_value = self._read_typed_value(base_item['address'], base_item['type'], base_item['signed'])
        except OSError as exc:
            raise SearchException("Could not read the base item's current value") from exc

        raw_known = req.media.get('known_values', {})
        if isinstance(raw_known, str):
            raw_known = raw_known.strip()
            if raw_known:
                try:
                    known_map = json.loads(raw_known)
                except json.JSONDecodeError as exc:
                    raise SearchException("Known value data could not be parsed") from exc
            else:
                known_map = {}
        elif isinstance(raw_known, dict):
            known_map = raw_known
        else:
            known_map = {}
        parsed_known = self._parse_known_values(known_map, group_entry['items'])
        if base_item['index'] in parsed_known:
            if not self._value_matches(parsed_known[base_item['index']], base_value, base_item['type']):
                raise SearchException("Known value for the base item does not match the current process value")

        results_identifier = uuid.uuid4().hex
        results_path = memory_directory.joinpath(f'structure_{results_identifier}.db')
        results_store = SearchResults(name=f'structure_{results_identifier}', db_path=results_path)
        searcher = SearcherMulti(self.mem(), progress=None, write_only=True, results=results_store)
        searcher.set_search_size(base_item['type'])
        searcher.set_signed(base_item['signed'])
        searcher.set_write_only(False)

        matches = []
        try:
            searcher.search_memory_value(str(base_value))
            with results_store.db() as conn:
                for address, _ in results_store.get_results(conn):
                    candidate_base = int(address)
                    if self._structure_candidate_matches(candidate_base, group_entry['items'], base_item, parsed_known):
                        matches.append(candidate_base)
        finally:
            searcher.reset()
            results_store.delete_database()

        matches = sorted(set(matches))
        resp.media['file'] = file_name
        resp.media['group'] = group_entry['name']
        resp.media['base_index'] = base_item['index']
        resp.media['base_address'] = '{:X}'.format(base_item['address'])
        resp.media['base_value'] = str(base_value)
        resp.media['results'] = []
        for candidate in matches:
            resp.media['results'].append({
                'base_address': '{:X}'.format(candidate),
                'base_index': base_item['index'],
                'items': [
                    {
                        'index': item['index'],
                        'name': item['name'],
                        'type': item['type'],
                        'signed': item['signed'],
                        'offset': item['offset'],
                        'address': '{:X}'.format(candidate + item['offset'])
                    }
                    for item in group_entry['items']
                ]
            })

    def handle_structure_apply(self, req: Request, resp: Response):
        # Assumption: applying a structure search hit requires the CodeList service to have the target file loaded.
        file_name = (req.media.get('file') or "").strip()
        group_name = (req.media.get('group') or "").strip()
        if not file_name:
            raise SearchException("Code list name is required to apply a structure rebase")
        try:
            index = int(req.media.get('index'))
        except (TypeError, ValueError):
            raise SearchException("A valid code index is required to apply a structure rebase")
        address = (req.media.get('address') or "").strip().upper()
        if not address:
            raise SearchException("A resolved address is required to apply a structure rebase")

        codelist_service = DataStore().get_service('codelist')
        if not getattr(codelist_service, 'code_data', None) or codelist_service.loaded_file != file_name:
            raise SearchException("Load the selected code list before applying a structure rebase")

        proxy_req = type('ProxyReq', (), {'media': {'index': index, 'type': 'address', 'address': address}})()
        if group_name:
            proxy_req.media['rebase_group'] = group_name
        proxy_resp = type('ProxyResp', (), {'media': {}})()
        try:
            codelist_service.handle_rebase(proxy_req, proxy_resp)
        except CodelistException as exc:
            raise SearchException(exc.get_message()) from exc
        resp.media.update(proxy_resp.media)

    def _normalize_structure_group(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            trimmed = value.strip()
            if not trimmed:
                return CodeList._DEFAULT_REBASE_GROUP
            if trimmed.casefold() == CodeList._DEFAULT_REBASE_GROUP:
                return CodeList._DEFAULT_REBASE_GROUP
            return trimmed
        return CodeList._DEFAULT_REBASE_GROUP

    def _load_structure_groups(self, file_name: str):
        path = CodeList.directory.joinpath(file_name + '.codes')
        if not path.exists():
            raise SearchException("Code list file was not found")
        try:
            with open(path, 'rt') as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise SearchException("Unable to read the requested code list") from exc
        if isinstance(data, dict):
            codes = data.get('codes', [])
        else:
            codes = data

        base_converter = BaseConvert()
        groups = {}
        for index, raw in enumerate(codes):
            if not isinstance(raw, dict):
                continue
            if raw.get('Source') != 'address':
                continue
            group_name = self._normalize_structure_group(raw.get('rebase_group', CodeList._DEFAULT_REBASE_GROUP))
            if group_name is None:
                continue
            address_value = raw.get('Address')
            if not address_value:
                continue
            try:
                resolved_address = self._resolve_structure_address(base_converter, str(address_value))
            except (ValueError, BaseConvertException) as exc:
                raise SearchException(f"Unable to resolve address for code index {index}") from exc
            item_type = raw.get('Type', 'byte_4')
            signed = bool(raw.get('Signed', False))
            name = raw.get('Name', f'Code #{index}')
            entry_key = group_name.casefold()
            group_entry = groups.setdefault(entry_key, {'name': group_name, 'items': []})
            if group_name != group_entry['name']:
                group_entry['name'] = group_name
            group_entry['items'].append({
                'index': index,
                'name': name,
                'type': item_type,
                'signed': signed,
                'address': resolved_address,
                'group': group_name,
            })

        filtered = {}
        for key, entry in groups.items():
            if not entry['items']:
                continue
            entry['items'].sort(key=lambda item: (item['address'], item['index']))
            base_item = entry['items'][0]
            for item in entry['items']:
                item['offset'] = item['address'] - base_item['address']
            entry['base'] = base_item
            filtered[key] = entry

        if not filtered:
            raise SearchException("No eligible address entries were found in the selected code list")
        return filtered

    def _resolve_structure_address(self, converter: BaseConvert, address: str) -> int:
        address = address.strip()
        if ':' in address:
            if not self.has_mem():
                raise SearchException("Attach to a process before resolving module-relative addresses")
            return converter.convert(self.mem(), address)
        return int(address, 16)

    def _read_typed_value(self, address: int, value_type: str, signed: bool):
        buffer = memory_utils.get_ctype_from_size(value_type)
        self.mem().read_memory(address, buffer)
        ctype_value = memory_utils.get_ctype_from_buffer(buffer, value_type, signed)
        return ctype_value.value

    def _parse_known_values(self, known_values: dict, items: list):
        parsed = {}
        indexed_items = {item['index']: item for item in items}
        for key, raw_value in known_values.items():
            try:
                idx = int(key)
            except (TypeError, ValueError):
                continue
            if idx not in indexed_items:
                continue
            value_str = str(raw_value).strip()
            if value_str == "":
                continue
            item = indexed_items[idx]
            if item['type'] == 'float':
                try:
                    parsed[idx] = float(value_str)
                except ValueError as exc:
                    raise SearchException(f"Invalid float value for {item['name']}") from exc
            else:
                try:
                    parsed[idx] = int(value_str, 0)
                except ValueError as exc:
                    raise SearchException(f"Invalid integer value for {item['name']}") from exc
        return parsed

    def _value_matches(self, expected, actual, value_type: str) -> bool:
        if value_type == 'float':
            return math.isclose(expected, actual, abs_tol=0.001)
        return expected == actual

    def _structure_candidate_matches(self, base_address: int, items: list, base_item: dict, known_values: dict) -> bool:
        for item in items:
            if item['index'] == base_item['index']:
                continue
            if item['index'] not in known_values:
                continue
            candidate_address = base_address + item['offset']
            try:
                candidate_value = self._read_typed_value(candidate_address, item['type'], item['signed'])
            except OSError:
                return False
            if not self._value_matches(known_values[item['index']], candidate_value, item['type']):
                return False
        return True

    class UpdateThread(Thread):
        def __init__(self, mem, addrs, pv: Value, s: Searcher):
            super().__init__(target=self.process)
            self.memory = mem
            self.addresses = copy.deepcopy(addrs)
            self.parsed_value = Value.copy(pv, _signed=s.signed)
            self.results_to_update(pv.get_store_type(), self.addresses)
            self.lock = Lock()
            self.write_list = []
            self.freeze_map = {}
            self.error = ""
            self.update_queue: PriorityQueue = PriorityQueue()
            self.add_action('refresh')

        @classmethod
        def results_to_update(cls, size, results):
            if size == 'array':
                for i in range(0, len(results)):
                    v = results[i]
                    byte_str = ' '.join(memory_utils.bytes_to_aob(v['value']))
                    results[i]['value'] = byte_str
            else:
                for v in results:
                    v['value'] = memory_utils.bytes_to_printable_value(v['value'], size)


        def _loop(self):
            try:
                while True:
                    update_data = self.update_queue.get()
                    if update_data[1] == 'quit':
                        break
                    if update_data[1] == 'refresh':
                        self.lock.acquire()
                        if len(self.write_list) > 0:
                            for item in self.write_list:
                                val: Value = item[1]
                                val.write_bytes_to_memory(self.memory, item[0])
                            self.write_list.clear()
                        if len(self.freeze_map) > 0:
                            for addr, value in self.freeze_map.items():
                                self.memory.write_memory(addr, value)
                        for i in range(0, len(self.addresses)):
                            addr = self.addresses[i]
                            self.parsed_value.read_memory(self.memory, addr['address'])
                            self.addresses[i]['value'] = self.parsed_value.get_printable()
                        self.lock.release()
            except Exception as e:
                self.error = str(e)
            finally:
                self.freeze_map.clear()
                if self.lock.locked():
                    self.lock.release()


        def add_action(self, action:str):
            if action.casefold().strip() == 'quit':
                self.update_queue.put((1, 'quit'))
            elif action.casefold().strip() == 'refresh':
                self.update_queue.put((2, 'refresh'))
            else:
                self.update_queue.put((3, action.casefold().strip()))
        def process(self):
            try:
                self._loop()
            except Exception as e:
                logging.error("Lost Update Thread {}".format(str(e)))
                traceback.print_exc()
                self.error = "Could not update process.  Did it close?"

        def get_addresses(self):
            self.lock.acquire()
            res = copy.deepcopy(self.addresses)
            self.lock.release()
            return res

        def write(self, address, value):
            self.lock.acquire()
            self.write_list.append((address, value))
            self.lock.release()

        def freeze(self, address, value, freeze):
            self.lock.acquire()
            if not freeze and address in self.freeze_map:
                del self.freeze_map[address]
            elif freeze and address not in self.freeze_map:
                self.freeze_map[address] = value
            self.lock.release()



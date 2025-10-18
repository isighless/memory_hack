import fnmatch
import logging
import os
import platform
import threading
import time
from pathlib import Path
from threading import Thread, Event

import mem_edit
import psutil
from falcon import Request, Response, MEDIA_JSON

from app.helpers.exceptions import ProcessException
from app.helpers.memory_utils import is_process_valid
from app.helpers.process_utils import is_pid_valid, can_attach
from app.services.service import Service

logger = logging.getLogger(__name__)


class Process(Service):
    def __init__(self):
        self.user = os.environ.get('USER', os.environ.get('USERNAME'))
        self.blacklist_path = self._blacklist_path()
        self.blacklist = self.load_blacklist()
        self.pid = 0
        self.pids = []
        self.pid_map = {}
        self.pid_map_copy = {}
        self.open_pids = {}
        self.service_pids = {}
        self.process_names = []
        self.last_update_time = 0
        self.last_id = 0xffffffff
        self.error = ""
        self.pid_map_lock = threading.Lock()

        self.load_region_blacklist()

        self.handle_map = {
            "GET_PROCESSES": self.handle_processes,
            "REQUEST_PROCESS": self.handle_request
        }

        self.process_classes = []
        self.thread_break = False
        self._process_monitor_event: Event = Event()
        self._process_monitor_thread: Thread = None
        self._pid_monitor_thread: Thread = Thread(target=self._pid_monitor)
        self._pid_monitor_event: Event = Event()
        self._pid_monitor_thread.start()

    def kill(self):
        self.thread_break = True
        self._process_monitor_event.set()
        self._pid_monitor_event.set()
        if self._pid_monitor_thread and self._pid_monitor_thread.is_alive():
            self._pid_monitor_thread.join()
        if self._process_monitor_thread and self._process_monitor_thread.is_alive():
            self._process_monitor_thread.join()

    def process(self, req: Request, resp: Response):
        resp.media = {}
        resp.content_type = MEDIA_JSON
        if self.error:
            resp.media['error'] = self.error
            self.error = ""
            return
        command = req.media['command']
        assert (command in self.handle_map)
        try:
            self.handle_map[command](req, resp)
        except ProcessException as e:
            resp.media['error'] = e.get_message()

    def handle_processes(self, req: Request, resp: Response):
        _id = int(req.media['id'])
        resp.media = {'status': 'INFO_GET_SUCCESS', 'processes': self.get_process_list(), 'last_update': self.get_last_update_time()}
        resp.media['services'] = [{'name':x[0], 'process': x[1]['exe']} for x in self.service_pids.items()]
        self.pid_map_copy = self.pid_map.copy()
        self.last_id = _id

    def handle_request(self, req: Request, resp: Response):
        _process = req.media['process']
        _service = req.media['service']
        try:
            self.request_process(_service, _process)
            resp.media['success'] = True
        except:
            resp.media['success'] = False
            resp.media['error'] = "Could not request this process."

    def get_process(self, cls):
        if cls not in self.process_classes:
            raise ProcessException('Cannot find class')
        return 0

    def add_process_service(self, cls):
        self.process_classes.append(cls)

    def get_process_list(self):
        pid_sorted = sorted([v for v in list(self.pid_map.values()) if v['valid']], key=lambda x: x['mem_percent'], reverse=True)
        return [v['exe'] for v in pid_sorted]


    def get_process_map(self):
        return self.pid_map


    def get_last_update_time(self):
        return self.last_update_time


    def get_open_process_classes(self, pid: int):
        cls = []
        for c in [x for x in self.process_classes if x.process_data]:
            if c.process_data['pid'] == pid:
                cls.append(c)
        return cls

    def error_process(self, pid: int, msg: str):
        self.error = msg
        for c in self.get_open_process_classes(pid):
            c.p_error(msg)
        self.close_process(pid)

    def close_process(self, pid: int):
        for c in self.get_open_process_classes(pid):
            c.p_release()
        if pid in self.open_pids:
            try:
                proc: mem_edit.Process = self.open_pids[pid]['process']
                del self.open_pids[pid]
                proc.close()
            except mem_edit.MemEditError:
                pass

    def open_process(self, p: str, service: str):
        logger.info("open_process(service=%s, exe=%s)", service, p)
        p_data = None
        try:
            matches = [(k, v) for k, v in self.pid_map.items() if v['exe'] == p and v['valid']]
            if not matches:
                logger.warning("open_process: no valid pid match for exe=%s; candidates=%d", p, len(self.pid_map))
                raise ProcessException("Process {} does not exist".format(p))
            pid = matches[0][0]
            if pid in self.open_pids:
                p_data = self.open_pids[pid]
            else:
                proc = mem_edit.Process(pid)
                p_data = {'process': proc, 'pid': pid, 'exe': p}
                self.open_pids[pid] = p_data
        except ProcessException:
            raise
        except Exception:
            logger.exception("open_process: unexpected error while opening exe=%s", p)
            raise ProcessException("Process {} does not exist".format(p))
        self.service_pids[service] = p_data
        return p_data


    def request_process(self, service: str, p: str):
        logger.info("request_process(service=%s, exe=%s)", service, p)
        if service not in [x.get_service_name() for x in self.process_classes]:
            raise ProcessException('Class does not exist.')
        if service in self.service_pids:
            current_pid = self.service_pids[service]['pid']
            if len([x for x in self.service_pids.items() if x[0] != service and x[1]['pid'] == current_pid]) == 0:
                self.close_process(current_pid)
            del self.service_pids[service]
        if p and p != '_null':
            proc = self.open_process(p, service)
            cls = [x for x in self.process_classes if x.get_service_name() == service][0]
            logger.info("request_process: delivering pid=%s to service=%s", proc['pid'], service)
            cls.p_set(proc)
            if not self._process_monitor_thread:
                self._process_monitor_event = Event()
                self._process_monitor_thread = Thread(target=self._process_monitor)
                self._process_monitor_thread.start()



    def _process_monitor(self):
        while self.open_pids and not self.thread_break:
            pids = self.open_pids.copy().keys()
            for pid in pids:
                with self.pid_map_lock:
                    if not is_process_valid(pid):
                        if pid in self.pid_map:
                            err = 'Process "{}" is no longer valid'.format(self.pid_map[pid]['exe'])
                        else:
                            err = 'Process is not longer valid'
                        self.error_process(pid, err)
                        self.remove_open_pid(pid)
            self._process_monitor_event.wait(0.6)
        self._process_monitor_thread = None


    def remove_open_pid(self, pid):
        self.close_process(pid)
        removals = []
        for service, value in self.service_pids.items():
            if value['pid'] == pid:
                removals.append(service)
        for x in removals:
            del self.service_pids[x]

    def _pid_monitor(self):
        while not self.thread_break:
            current_pid_set = set(mem_edit.Process.list_available_pids())
            previous_pid_set = set(self.pids)
            difference = current_pid_set ^ previous_pid_set
            with self.pid_map_lock:
                for d in difference:
                    if d in current_pid_set:
                        # this is a new pid
                        try:
                            proc = psutil.Process(d)
                            with proc.oneshot():
                                if os.name == "nt":
                                    try:
                                        user = proc.username()
                                    except psutil.AccessDenied:
                                        user = 'NT AUTHORITY\\SYSTEM'
                                else:
                                    user = proc.username()
                                exe_name = proc.as_dict()['exe']
                                if platform.system() == 'Linux':
                                    if exe_name and '/' in exe_name:
                                        exe_name = exe_name.split('/')[-1]
                                else:
                                    if exe_name and '\\' in exe_name:
                                        exe_name = exe_name.split('\\')[-1]
                                if exe_name and proc.name() != exe_name:
                                    exe_name += ':{}'.format(proc.name())
                                self.pid_map[d] = {'pid': d, 'exe': exe_name, 'name': proc.name(), 'user': user, 'status': proc.status(), 'mem_percent': proc.memory_percent(), 'valid': exe_name is not None and is_pid_valid(proc.pid) and not self.is_blacklisted(proc.name()) and can_attach(proc.pid)}
                                self.pids.append(d)
                        except psutil.NoSuchProcess:
                            continue
                    else:
                        # this pid is gone
                        self.pids.remove(d)
                        del self.pid_map[d]
            if len(difference) > 0:
                self.last_update_time = int(time.time() * 100) - 160000000000
            self._pid_monitor_event.wait(1)

    def is_blacklisted(self, name):
        if not self.blacklist:
            return False
        return any(fnmatch.fnmatch(name, x) for x in self.blacklist)

    def _blacklist_path(self) -> Path:
        root = Path("./resources")
        filename = 'win_blacklist.txt' if os.name == 'nt' else 'lin_blacklist.txt'
        return root.joinpath(filename)

    def load_blacklist(self):
        path = getattr(self, 'blacklist_path', None) or self._blacklist_path()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            return []
        bl = path.read_text(encoding='utf-8').splitlines()
        entries = [b.strip() for b in bl if b.strip()]
        unique = []
        seen = set()
        for entry in entries:
            key = entry.casefold()
            if key in seen:
                continue
            seen.add(key)
            unique.append(entry)
        return unique

    def save_blacklist(self):
        path = getattr(self, 'blacklist_path', None) or self._blacklist_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(set(self.blacklist), key=lambda x: x.casefold())
        path.write_text("\n".join(ordered) + ("\n" if ordered else ""), encoding='utf-8')
        self.blacklist = ordered
        self._apply_blacklist_to_pid_map()

    def get_blacklist_snapshot(self):
        entries = sorted(self.blacklist, key=lambda x: x.casefold())
        # Copy pid_map values quickly while holding the lock minimally
        with self.pid_map_lock:
            snapshot = list(self.pid_map.values())
        available_map = {}
        for details in snapshot:
            name = details.get('name')
            if not name:
                continue
            key = name.casefold()
            if self.is_blacklisted(name):
                continue
            if key not in available_map:
                display = details.get('exe') or name
                available_map[key] = {"name": name, "display": display}
        available = sorted(available_map.values(), key=lambda x: x["name"].casefold())
        return entries, available

    def add_to_blacklist(self, name: str) -> bool:
        entry = (name or '').strip()
        if not entry:
            return False
        if any(entry.casefold() == existing.casefold() for existing in self.blacklist):
            return False
        self.blacklist.append(entry)
        self.save_blacklist()
        return True

    def remove_from_blacklist(self, name: str) -> bool:
        entry = (name or '').strip()
        if not entry:
            return False
        remaining = [b for b in self.blacklist if b.casefold() != entry.casefold()]
        if len(remaining) == len(self.blacklist):
            return False
        self.blacklist = remaining
        self.save_blacklist()
        return True

    def add_all_processes_to_blacklist(self) -> bool:
        added = False
        with self.pid_map_lock:
            names = {details.get('name') for details in self.pid_map.values() if details.get('name')}
        for name in names:
            if not name:
                continue
            if any(name.casefold() == existing.casefold() for existing in self.blacklist):
                continue
            self.blacklist.append(name)
            added = True
        if added:
            self.save_blacklist()
        return added

    def _apply_blacklist_to_pid_map(self):
        with self.pid_map_lock:
            for pid, info in self.pid_map.items():
                try:
                    valid = info.get('exe') is not None and is_pid_valid(pid) and not self.is_blacklisted(info.get('name', '')) and can_attach(pid)
                except Exception:
                    valid = False
                info['valid'] = valid
            self.last_update_time = int(time.time() * 100) - 160000000000


    def load_region_blacklist(self):
        p = Path("./resources")
        if os.name == 'nt':
            p = p.joinpath('win_region_blacklist.txt')
        else:
            p = p.joinpath('lin_region_blacklist.txt')
        if not p.exists():
            return []
        bl = p.read_text().splitlines()
        blacklist = [b.strip() for b in bl]
        mem_edit.Process.set_blacklist(blacklist)




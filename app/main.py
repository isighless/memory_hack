import falcon

from app.helpers.data_store import DataStore
from app.helpers.process_utils import get_process_names
from app.helpers.logging_utils import (
    clear_log_file,
    get_log_file_path,
    get_log_metadata,
    read_log_tail,
)
from app.services.aob import AOB
from app.services.codes import CodeList
from app.services.process import Process
from app.services.script import Script
from app.services.searcher import Search
from app.version import __version__


def initialize():
    data_store = DataStore()
    data_store.set_service('process', Process())
    data_store.set_service('search', Search())
    data_store.set_service('aob', AOB())
    data_store.set_service('script', Script())
    data_store.set_service('codelist', CodeList())



class MainResource:
    pattern = r'\s*<ons-tab.*page="/(\w+)"(.*)>'
    def on_get(self, req, resp):
        global __version__
        resp.content_type = falcon.MEDIA_HTML
        with open('resources/index.html', 'rt') as ac:
            resp.text = ac.read().replace('#search_active#', '').replace('#aob_active#', '').replace('#script_active#', '').replace("#version#", __version__)

class SearchResource:
    def on_get(self, req, resp):
        search_instance = DataStore().get_service('search')
        resp.content_type = falcon.MEDIA_HTML
        resp.text = search_instance.html_main()

    def on_post(self, req: falcon.Request, resp: falcon.Response):
        search_instance = DataStore().get_service('search')
        search_instance.process(req, resp)
        if resp.status == 200:
            resp.media['process'] = search_instance.get_process_name()
class ScriptResource:
    def on_get(self, req, resp):
        script_instance = DataStore().get_service('script')
        resp.content_type = falcon.MEDIA_HTML
        resp.text = script_instance.html_main()

    def on_post(self, req: falcon.Request, resp: falcon.Response):
        script_instance = DataStore().get_service('script')
        resp.content_type = falcon.MEDIA_JSON
        script_instance.process(req, resp)

class AOBResource:

    def on_get(self, req, resp):
        aob_instance = DataStore().get_service('aob')
        if 'name' in req.params:
            aob_instance.handle_download(req, resp)
        else:
            resp.content_type = falcon.MEDIA_HTML
            resp.text = aob_instance.html_main()

    def on_post(self, req: falcon.Request, resp: falcon.Response):
        aob_instance = DataStore().get_service('aob')
        aob_instance.process(req, resp)
        if resp.status == 200:
            resp.media['process'] = aob_instance.get_process_name()


class CodeListResource:

    def on_get(self, req, resp):
        codelist_instance = DataStore().get_service('codelist')
        if 'name' in req.params:
            codelist_instance.handle_download(req, resp)
        else:
            resp.content_type = falcon.MEDIA_HTML
            resp.text = codelist_instance.html_main()

    def on_post(self, req: falcon.Request, resp: falcon.Response):
        codelist_instance = DataStore().get_service('codelist')
        codelist_instance.process(req, resp)
        if resp.status == 200:
            resp.media['process'] = codelist_instance.get_process_name()

class InfoResource:
    data_store = DataStore()
    def on_post(self, req: falcon.Request, resp: falcon.Response):
        process_instance = DataStore().get_service('process')
        process_instance.process(req, resp)

    def get_process_and_crc(self, iteration=-1):
        current_proc = self.data_store.get_process()
        # if we are attached to a process already, then we will not update the process list
        if not current_proc:
            procs, crc = get_process_names()
        elif iteration == 0:
            procs, crc = get_process_names()
            if current_proc not in procs:
                procs.insert(0, current_proc)
            else:
                procs.insert(0, procs.pop(procs.index(current_proc)))
            crc = -1
        else:
            procs, crc = [], 0
        return procs, crc


class SettingsResource:
    def on_get(self, req, resp):
        resp.content_type = falcon.MEDIA_HTML
        with open('resources/settings.html', 'rt') as ac:
            resp.text = ac.read()

    def on_post(self, req, resp):
        resp.media = {}
        resp.content_type = falcon.app_helpers.MEDIA_JSON
        command = (req.media or {}).get('command', '')

        if command == 'RESTART_SERVER':
            DataStore().get_operation_control().request_restart()
            resp.media['status'] = 'ok'
            resp.media['message'] = 'Restart requested'
        elif command == 'GET_SERVER_LOG':
            limit = req.media.get('limit', 400) if req.media else 400
            try:
                line_limit = int(limit)
            except (TypeError, ValueError):
                line_limit = 400

            lines = read_log_tail(line_limit)
            metadata = get_log_metadata()
            resp.media['status'] = 'ok'
            resp.media['log'] = "\n".join(lines)
            resp.media['line_count'] = len(lines)
            resp.media['metadata'] = metadata
        elif command == 'CLEAR_SERVER_LOG':
            clear_log_file()
            metadata = get_log_metadata()
            resp.media['status'] = 'ok'
            resp.media['metadata'] = metadata
        elif command == 'GET_PROCESS_BLACKLIST':
            process_service = DataStore().get_service('process')
            entries, available = process_service.get_blacklist_snapshot()
            resp.media['status'] = 'ok'
            resp.media['blacklist'] = entries
            resp.media['available'] = available
        elif command == 'ADD_PROCESS_BLACKLIST':
            process_name = (req.media or {}).get('process')
            process_service = DataStore().get_service('process')
            added = process_service.add_to_blacklist(process_name)
            entries, available = process_service.get_blacklist_snapshot()
            resp.media['status'] = 'ok' if added else 'noop'
            resp.media['blacklist'] = entries
            resp.media['available'] = available
        elif command == 'REMOVE_PROCESS_BLACKLIST':
            process_name = (req.media or {}).get('process')
            process_service = DataStore().get_service('process')
            removed = process_service.remove_from_blacklist(process_name)
            entries, available = process_service.get_blacklist_snapshot()
            resp.media['status'] = 'ok' if removed else 'noop'
            resp.media['blacklist'] = entries
            resp.media['available'] = available
        elif command == 'BLACKLIST_ALL_PROCESSES':
            process_service = DataStore().get_service('process')
            added_any = process_service.add_all_processes_to_blacklist()
            entries, available = process_service.get_blacklist_snapshot()
            resp.media['status'] = 'ok' if added_any else 'noop'
            resp.media['blacklist'] = entries
            resp.media['available'] = available
        else:
            resp.media['status'] = 'error'
            resp.media['message'] = 'Unknown command'


class SettingsLogDownloadResource:
    def on_get(self, req, resp):
        path = get_log_file_path()
        metadata = get_log_metadata()
        if not metadata.get('exists', False):
            resp.status = falcon.HTTP_404
            resp.media = {'status': 'error', 'message': 'Log file not found'}
            return

        resp.content_type = 'text/plain; charset=utf-8'
        resp.downloadable_as = path.name
        resp.stream = path.open('rb')
        resp.stream_len = path.stat().st_size

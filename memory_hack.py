from pathlib import Path
import os
import logging
from logging.handlers import RotatingFileHandler
import falcon

from falcon_multipart.middleware import MultipartMiddleware
import importlib
import sys
import threading
from wsgiref.simple_server import make_server, WSGIRequestHandler

class NoLoggingWSGIRequestHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass

if __name__ == '__main__':
    # Configure logging for console and rotating file output
    base_dir = Path(__file__).parent
    log_dir = base_dir.joinpath('logs')
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir.joinpath('memory_hack.log')

    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s', force=True)
    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    logging.getLogger().addHandler(file_handler)

    logger = logging.getLogger(__name__)

    # Route unhandled exceptions to our logger so they appear in the server logs
    def _sys_excepthook(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            logger.info('KeyboardInterrupt received (sys).')
            return
        logger.exception('Unhandled exception', exc_info=(exc_type, exc_value, exc_traceback))

    def _thread_excepthook(args: threading.ExceptHookArgs):
        if issubclass(args.exc_type, KeyboardInterrupt):
            logger.info('KeyboardInterrupt received in thread %s', args.thread.name)
            return
        logger.exception('Unhandled exception in thread %s', args.thread.name,
                         exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = _sys_excepthook
    threading.excepthook = _thread_excepthook
    pt = Path(__file__).parent.joinpath('app')
    os.chdir(pt)
    # Outer loop to allow controlled restarts without relaunching the process
    while True:
        # Fully unload app.* modules to avoid identity mismatches across restarts
        # (important for multiprocessing pickling and type checks)
        try:
            importlib.invalidate_caches()
            for name in [n for n in list(sys.modules.keys()) if n == 'app' or n.startswith('app.')]:
                sys.modules.pop(name, None)
        except Exception:
            logger.exception('Module unload sweep failed')

        # Import fresh references after reload
        app_module = importlib.import_module('app.main')
        initialize = getattr(app_module, 'initialize')
        MainResource = getattr(app_module, 'MainResource')
        SearchResource = getattr(app_module, 'SearchResource')
        CodeListResource = getattr(app_module, 'CodeListResource')
        ScriptResource = getattr(app_module, 'ScriptResource')
        AOBResource = getattr(app_module, 'AOBResource')
        InfoResource = getattr(app_module, 'InfoResource')
        SettingsResource = getattr(app_module, 'SettingsResource')
        SettingsLogDownloadResource = getattr(app_module, 'SettingsLogDownloadResource')

        app = falcon.App(middleware=[MultipartMiddleware()])
        initialize()
        app.add_route('/', MainResource())
        app.add_route('/search', SearchResource())
        app.add_route('/codelist', CodeListResource())
        app.add_route('/script', ScriptResource())
        app.add_route('/settings', SettingsResource())
        app.add_route('/settings/log/download', SettingsLogDownloadResource())
        app.add_route('/aob', AOBResource())
        app.add_route('/info', InfoResource())
        app.add_static_route('/resources/static', pt.joinpath("resources/static/").absolute())

        ds_module = importlib.import_module('app.helpers.data_store')
        DataStoreCls = getattr(ds_module, 'DataStore')
        ds = DataStoreCls()
        op_control = ds.get_operation_control()
        try:
            with make_server('', 5000, app, handler_class=NoLoggingWSGIRequestHandler) as httpd:
                logger.info('Serving on port 5000...')
                # Handle one request at a time so we can observe restart signals
                while True:
                    httpd.handle_request()
                    if op_control.is_restart_requested():
                        logger.info('Restart requested from settings page. Cleaning up and restarting server...')
                        break
        except KeyboardInterrupt:
            logger.info('KeyboardInterrupt received. Shutting down and cleaning up services...')
            ds.kill()
            break
        except Exception:
            # Catch-all to provide debug information for unexpected exceptions
            logger.exception('Unhandled exception in Memory Hack server loop')
            ds.kill()
            break
        # Normal exit path after a restart request
        if op_control.is_restart_requested():
            ds.kill()
            op_control.clear_restart()
            continue
        else:
            break

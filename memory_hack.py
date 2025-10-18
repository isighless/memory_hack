from pathlib import Path
import os
import logging
import falcon

from falcon_multipart.middleware import MultipartMiddleware
import importlib
import sys
from wsgiref.simple_server import make_server, WSGIRequestHandler

class NoLoggingWSGIRequestHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass

if __name__ == '__main__':
    # Configure logging for console output
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    logger = logging.getLogger(__name__)
    pt = Path(__file__).parent.joinpath('app')
    os.chdir(pt)
    # Outer loop to allow controlled restarts (with optional module reloads)
    while True:
        # Soft-reload app.* modules so updated code is picked up without full exit
        try:
            importlib.invalidate_caches()
            # Ensure no stale user script modules linger across restarts
            for name in [n for n in list(sys.modules.keys()) if n.startswith('app.user_scripts')]:
                sys.modules.pop(name, None)
            to_reload = [
                name for name in list(sys.modules.keys())
                if name.startswith('app.') and not name.startswith('app.user_scripts')
            ]
            # Reload leaves first (longer names first), then parents
            for name in sorted(to_reload, key=lambda n: (-n.count('.'), -len(n))):
                try:
                    importlib.reload(sys.modules[name])
                except Exception:
                    logger.exception('Module reload failed for %s', name)
        except Exception:
            logger.exception('Module reload sweep failed')

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

        app = falcon.App(middleware=[MultipartMiddleware()])
        initialize()
        app.add_route('/', MainResource())
        app.add_route('/search', SearchResource())
        app.add_route('/codelist', CodeListResource())
        app.add_route('/script', ScriptResource())
        app.add_route('/settings', SettingsResource())
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

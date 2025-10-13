from pathlib import Path
import os
import logging
import falcon

from falcon_multipart.middleware import MultipartMiddleware
from app import ScriptResource, SearchResource, MainResource, AOBResource, InfoResource, CodeListResource
from app.main import initialize
from app.helpers.data_store import DataStore
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
    app = falcon.App(middleware=[MultipartMiddleware()])
    initialize()
    app.add_route('/', MainResource())
    app.add_route('/search', SearchResource())
    app.add_route('/codelist', CodeListResource())
    app.add_route('/script', ScriptResource())
    app.add_route('/aob', AOBResource())
    app.add_route('/info', InfoResource())
    app.add_static_route('/resources/static', pt.joinpath("resources/static/").absolute())

    try:
        with make_server('', 5000, app, handler_class=NoLoggingWSGIRequestHandler) as httpd:
            logger.info('Serving on port 5000...')
            httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info('KeyboardInterrupt received. Shutting down and cleaning up services...')
        DataStore().kill()
    except Exception:
        # Catch-all to provide debug information for unexpected exceptions
        logger.exception('Unhandled exception in Memory Hack server loop')
        DataStore().kill()

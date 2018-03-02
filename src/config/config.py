"""Config parser."""
from configparser import ConfigParser
from os.path import dirname, abspath, join, isfile
import logging

logger = logging.getLogger(__name__)
config = ConfigParser()
for conf in ('config.conf',):
    _path = join(
        dirname(abspath(__file__)),
        conf,
    )
    if isfile(_path):
        path = _path
if not path:
    raise FileNotFoundError('`config.conf` must be provided')

logger.debug(path)
config = ConfigParser()
config.read(path)

"""One module per external source.

Each module defines a `Connector` subclass and decorates it with
`fieldclub.ingest.registry.register`. `registry.discover()` imports every module
here, so adding a file is all it takes to add a source.
"""

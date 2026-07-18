# Storage Layer Abstraction API

The storage layer API serves as a generic way to make, access, store, edit, or delete
files.

The need for this abstraction is due to the fact that we want to be able to support
multiple underlying technologies and storage methods, like box, local storage, or
possibly S3. Having an abstraction allows us to easily move and migrate backends without
needing the change significant portions of the bfd9000 codebase.

The abstraction for what is required for a storage layer to implement is in
`bfd9000_web/archive/storage/storage.py`

This ABC requires the implementation of the following functions:

- exists
- \_raw_open
- \_raw_close
- delete
- list
- mkdir
- rmdir
- \_raw_read_stream
- \_raw_write_stream
- get_times
- size
- health

The implementation is required to specify and act upon the concept of file handles, such
that the file provider is able to keep track of which files are currently being used,
for later optimizations like pre-caching. The implementation is also required to
implement streaming readers and writers, in order to reduce latency during file
operations, allowing a manageable speed when retrieving files from high latency backends
like box.

The following functions are implemented by default as part of the ABC:

- open
- close
- read_stream
- read
- write_stream
- write

As this provides greater type safety in file handle management by utilizing managed
handles, allowing for automatic implementation of `__enter__` and `__exit__` without any
additional work on the backend's implementation, allowing for safer file usage by
scoping file closes.

## Implemented backends:

- Box: A backend using box.com
- Local: Uses a local directory as a storage backend, additionally protecting against
  directory traversal

## Implemented helper backends:

- Fallback: A backend that is created by stacking other backends in order to fallback
  when one fails
- URI Handler: A backend whos handle is a URI, allowing for easy global identification
  and routing of backends based on the URI schema

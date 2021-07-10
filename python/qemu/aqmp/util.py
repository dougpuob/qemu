"""
Miscellaneous Utilities

This module provides asyncio utilities and compatibility wrappers for
Python 3.6 to provide some features that otherwise become available in
Python 3.7+.

Various logging and debugging utilities are also provided, such as
`exception_summary()` and `pretty_traceback()`, used primarily for
adding information into the logging stream.
"""

import asyncio
import inspect
import io
import sys
import traceback
from types import CoroutineType, FrameType, GeneratorType
from typing import (
    IO,
    Any,
    Awaitable,
    Coroutine,
    Generator,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
    cast,
)


T = TypeVar('T')


# --------------------------
# Section: Utility Functions
# --------------------------


async def flush(writer: asyncio.StreamWriter) -> None:
    """
    Utility function to ensure a StreamWriter is *fully* drained.

    `asyncio.StreamWriter.drain` only promises we will return to below
    the "high-water mark". This function ensures we flush the entire
    buffer -- by setting the high water mark to 0 and then calling
    drain. The flow control limits are restored after the call is
    completed.
    """
    transport = cast(asyncio.WriteTransport, writer.transport)

    # https://github.com/python/typeshed/issues/5779
    low, high = transport.get_write_buffer_limits()  # type: ignore
    transport.set_write_buffer_limits(0, 0)
    try:
        await writer.drain()
    finally:
        transport.set_write_buffer_limits(high, low)


def upper_half(func: T) -> T:
    """
    Do-nothing decorator that annotates a method as an "upper-half" method.

    These methods must not call bottom-half functions directly, but can
    schedule them to run.
    """
    return func


def bottom_half(func: T) -> T:
    """
    Do-nothing decorator that annotates a method as a "bottom-half" method.

    These methods must take great care to handle their own exceptions whenever
    possible. If they go unhandled, they will cause termination of the loop.

    These methods do not, in general, have the ability to directly
    report information to a caller’s context and will usually be
    collected as a Task result instead.

    They must not call upper-half functions directly.
    """
    return func


# -------------------------------
# Section: Compatibility Wrappers
# -------------------------------


def create_task(coro: Coroutine[Any, Any, T],
                loop: Optional[asyncio.AbstractEventLoop] = None
                ) -> 'asyncio.Future[T]':
    """
    Python 3.6-compatible `asyncio.create_task` wrapper.

    :param coro: The coroutine to execute in a task.
    :param loop: Optionally, the loop to create the task in.

    :return: An `asyncio.Future` object.
    """
    if sys.version_info >= (3, 7):
        if loop is not None:
            return loop.create_task(coro)
        return asyncio.create_task(coro)  # pylint: disable=no-member

    # Python 3.6:
    return asyncio.ensure_future(coro, loop=loop)


def get_task_coro(task: 'asyncio.Task[Any]') -> Coroutine[Any, Any, Any]:
    """
    Python 3.6 and 3.7 compatible `asyncio.Task.get_coro` wrapper.

    :param task: The `asyncio.Task` to retrieve the `asyncio.coroutine` for.
    :return: The `asyncio.coroutine` object wrapped by this `asyncio.Task`.
    """
    if sys.version_info >= (3, 8):
        return task.get_coro()

    # Python 3.6, 3.7:
    return cast(Coroutine[Any, Any, Any], getattr(task, '_coro'))


def is_closing(writer: asyncio.StreamWriter) -> bool:
    """
    Python 3.6-compatible `asyncio.StreamWriter.is_closing` wrapper.

    :param writer: The `asyncio.StreamWriter` object.
    :return: `True` if the writer is closing, or closed.
    """
    if sys.version_info >= (3, 7):
        return writer.is_closing()

    # Python 3.6:
    transport = writer.transport
    assert isinstance(transport, asyncio.WriteTransport)
    return transport.is_closing()


async def wait_closed(writer: asyncio.StreamWriter) -> None:
    """
    Python 3.6-compatible `asyncio.StreamWriter.wait_closed` wrapper.

    :param writer: The `asyncio.StreamWriter` to wait on.
    """
    if sys.version_info >= (3, 7):
        await writer.wait_closed()
        return

    # Python 3.6
    transport = writer.transport
    assert isinstance(transport, asyncio.WriteTransport)

    while not transport.is_closing():
        await asyncio.sleep(0)
    await flush(writer)


def asyncio_run(coro: Coroutine[Any, Any, T], *, debug: bool = False) -> T:
    """
    Python 3.6-compatible `asyncio.run` wrapper.

    :param coro: A coroutine to execute now.
    :return: The return value from the coroutine.
    """
    if sys.version_info >= (3, 7):
        return asyncio.run(coro, debug=debug)

    # Python 3.6
    loop = asyncio.get_event_loop()
    loop.set_debug(debug)
    ret = loop.run_until_complete(coro)
    loop.close()

    return ret


# ----------------------------
# Section: Logging & Debugging
# ----------------------------


def exception_summary(exc: BaseException) -> str:
    """
    Return a summary string of an arbitrary exception.

    It will be of the form "ExceptionType: Error Message", if the error
    string is non-empty, and just "ExceptionType" otherwise.
    """
    name = type(exc).__qualname__
    smod = type(exc).__module__
    if smod not in ("__main__", "builtins"):
        name = smod + '.' + name

    error = str(exc)
    if error:
        return f"{name}: {error}"
    return name


def pretty_traceback(prefix: str = "  | ") -> str:
    """
    Formats the current traceback, indented to provide visual distinction.

    This is useful for printing a traceback within a traceback for
    debugging purposes when encapsulating errors to deliver them up the
    stack; when those errors are printed, this helps provide a nice
    visual grouping to quickly identify the parts of the error that
    belong to the inner exception.

    :param prefix: The prefix to append to each line of the traceback.
    :return: A string, formatted something like the following::

      | Traceback (most recent call last):
      |   File "foobar.py", line 42, in arbitrary_example
      |     foo.baz()
      | ArbitraryError: [Errno 42] Something bad happened!
    """
    output = "".join(traceback.format_exception(*sys.exc_info()))

    exc_lines = []
    for line in output.split('\n'):
        exc_lines.append(prefix + line)

    # The last line is always empty, omit it
    return "\n".join(exc_lines[:-1])


def walk_awaitable(obj: Union[
        Awaitable[Any],
        Generator[Any, Any, Any],
        None,
]) -> Generator[Tuple[FrameType, int], None, None]:
    """
    Walk an Awaitable/Generator and yield stack frames.

    Mimics `traceback.walk_tb`, except instead of walking an execution
    traceback with :py:attr:`tb_next`, it walks `await` statements to
    produce an "async traceback". Yields the frame and line number for
    each frame.
    """
    if isinstance(obj, asyncio.Task):
        obj = get_task_coro(obj)

    while obj is not None:
        if isinstance(obj, GeneratorType):
            yield obj.gi_frame, obj.gi_frame.f_lineno
            obj = cast(Generator[Any, Any, Any], obj.gi_yieldfrom)
        elif isinstance(obj, CoroutineType):
            if obj.cr_frame is None:
                # None when state is CORO_CLOSED
                break
            yield obj.cr_frame, obj.cr_frame.f_lineno
            obj = cast(Awaitable[Any], obj.cr_await)
        else:
            break


def extract_awaitable(
        aw: Awaitable[Any],
        limit: Optional[int] = None,
) -> traceback.StackSummary:
    """
    Return a `traceback.StackSummary` object representing a list of
    pre-processed entries from an awaitable.

    Written by analogy to `traceback.extract_tb`.
    """
    return traceback.StackSummary.extract(walk_awaitable(aw), limit=limit)


def format_awaitable(aw: Awaitable[Any],
                     limit: Optional[int] = None) -> List[str]:
    """
    A shorthand for 'format_list(extract_awaitable(aw, limit))'.

    Written by analogy to `traceback.format_tb`.
    """
    return extract_awaitable(aw, limit).format()


def print_awaitable(
        aw: Awaitable[Any],
        limit: Optional[int] = None,
        file: Optional[IO[str]] = None
) -> None:
    """
    Print up to 'limit' await trace entries from the awaitable 'aw'.

    If 'limit' is omitted or None, all entries are printed.  If 'file'
    is omitted or None, the output goes to sys.stderr; otherwise
    'file' should be an open file or file-like object with a write()
    method.

    Written by analogy to `traceback.print_tb`.
    """
    traceback.print_list(extract_awaitable(aw, limit=limit), file)


def debug_task(task: 'asyncio.Task[Any]') -> str:
    """
    Return formatted information (and an 'await trace') for a given Task.

    Returns a string that resembles a traceback, except the header has
    information about the Task under question, followed by a trace of
    what that Task is currently awaiting.

    :param task: The Task to return trace information for.
    :return: A string, ready to print or log.
    """
    output = io.StringIO("Task ")

    if sys.version_info >= (3, 8):
        name = task.get_name()
        print(repr(name), end=' ', file=output)

    coro = get_task_coro(task)
    status = inspect.getcoroutinestate(coro)

    print(f"at 0x{id(coro):x} [{status}]:", file=output)
    print_awaitable(task, file=output)

    return output.getvalue()

"""
Sync QMP Wrapper

This class pretends to be qemu.qmp.QEMUMonitorProtocol.
"""

import asyncio
from typing import List, Optional, Union

import qemu.qmp
from qemu.qmp import QMPMessage, QMPReturnValue, SocketAddrT

from .qmp_client import QMPClient


# pylint: disable=missing-docstring
# pylint: disable=protected-access


class QEMUMonitorProtocol(qemu.qmp.QEMUMonitorProtocol):
    def __init__(self, address: SocketAddrT,
                 server: bool = False,
                 nickname: Optional[str] = None):

        # pylint: disable=super-init-not-called
        self._aqmp = QMPClient(nickname)
        self._aloop = asyncio.get_event_loop()
        self._address = address

    # __enter__ and __exit__ need no changes
    # parse_address needs no changes

    def connect(self, negotiate: bool = True) -> Optional[QMPMessage]:
        if negotiate:
            self._aqmp.await_greeting = True
            self._aqmp.negotiate = True

        self._aloop.run_until_complete(
            self._aqmp.connect(self._address)
        )

        if negotiate:
            assert self._aqmp._greeting is not None
            return dict(self._aqmp._greeting._raw)

        return None

    def accept(self, timeout: Optional[float] = 15.0) -> QMPMessage:
        self._aqmp.await_greeting = True
        self._aqmp.negotiate = True

        self._aloop.run_until_complete(
            self._aqmp.accept(self._address)
        )

        assert self._aqmp._greeting is not None
        return dict(self._aqmp._greeting._raw)

    def cmd_obj(self, qmp_cmd: QMPMessage) -> QMPMessage:
        return dict(
            self._aloop.run_until_complete(
                self._aqmp._raw(qmp_cmd, assign_id=False)
            )
        )

    # Default impl of cmd() delegates to cmd_obj

    def command(self, cmd: str, **kwds: object) -> QMPReturnValue:
        return self._aloop.run_until_complete(
            self._aqmp.execute(cmd, kwds)
        )

    def pull_event(
            self,
            wait: Union[bool, float] = False
    ) -> Optional[QMPMessage]:
        if wait is False:
            # Return None if there's no event ready to go
            if self._aqmp.events._queue.empty():
                return None

        timeout = None
        if isinstance(wait, float):
            timeout = wait

        return dict(
            self._aloop.run_until_complete(
                asyncio.wait_for(
                    self._aqmp.events.get(),
                    timeout,
                )
            )
        )

    def get_events(self, wait: Union[bool, float] = False) -> List[QMPMessage]:
        events = []
        while True:
            try:
                events.append(
                    dict(
                        self._aqmp.events._queue.get_nowait()
                    )
                )
            except asyncio.QueueEmpty:
                break

        if events:
            return events

        event = self.pull_event(wait)
        return [event] if event is not None else []

    def clear_events(self) -> None:
        self._aqmp.events.clear()

    def close(self) -> None:
        self._aloop.run_until_complete(
            self._aqmp.disconnect()
        )

    def settimeout(self, timeout: Optional[float]) -> None:
        raise NotImplementedError

    def get_sock_fd(self) -> int:
        raise NotImplementedError

    def is_scm_available(self) -> bool:
        raise NotImplementedError

from typing import Callable
from collections import deque
import logging
import re
import socket
import threading


logger = logging.getLogger(__name__)

DEFAULT_PORT = 27072


class EventListener:
    """Receives behavior events over UDP on a background thread.

    Events are pushed into a bounded deque as ``(index, time, text)``; the
    GUI reads from :attr:`events` while rendering. The socket is rebound when
    :attr:`port` changes.

    Parameters
    ----------
    get_time : callable
        Returns the timestamp to record an event at, e.g. the plot clock.
    get_filter : callable, optional
        Returns the current filter; events are kept when the filter is a
        substring of, or a case-insensitive regex matching, the event.
    strip_character : callable, optional
        Returns True when the ``chrXXXX:`` prefix should be cut off.
    port : int
        UDP port to listen on.
    max_events : int
        How many events to retain.
    """

    def __init__(
        self,
        get_time: Callable[[], float],
        *,
        get_filter: Callable[[], str] = None,
        strip_character: Callable[[], bool] = None,
        port: int = DEFAULT_PORT,
        max_events: int = 100,
    ) -> None:
        self._get_time = get_time
        self._get_filter = get_filter
        self._strip_character = strip_character
        self._port = port

        self._sock: socket.socket = None
        self._thread: threading.Thread = None
        self._running = False
        self._event_idx = 0

        self.events: deque[tuple[int, float, str]] = deque(maxlen=max_events)

    # === Public =======================================================

    @property
    def port(self) -> int:
        return self._port

    @port.setter
    def port(self, new_port: int) -> None:
        if new_port == self._port:
            return

        self.stop()
        self._port = new_port
        self.start()

    def start(self) -> None:
        """Bind the socket and begin receiving on a daemon thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 0.5) -> None:
        """Stop receiving and close the socket."""
        self._running = False

        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

        if self._sock:
            self._sock.close()
            self._sock = None

    def clear(self) -> None:
        self.events.clear()

    # === Internal =====================================================

    def _accepts(self, event: str) -> bool:
        if not self._get_filter:
            return True

        filter_value = (self._get_filter() or "").strip()
        if not filter_value:
            return True

        return bool(
            filter_value in event
            or re.match(filter_value, event, flags=re.IGNORECASE)
        )

    def _listen(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(0.1)
        self._sock.bind(("localhost", self._port))

        try:
            while self._running:
                try:
                    data, _ = self._sock.recvfrom(1024)
                    event = data.decode("utf-8").strip()

                    if not self._accepts(event):
                        continue

                    print(f" ✦ {event}")

                    if self._strip_character and self._strip_character():
                        event = event.split(":", maxsplit=1)[-1]

                    self.events.append(
                        (self._event_idx, self._get_time(), event)
                    )
                    self._event_idx += 1
                except socket.timeout:
                    continue
                except Exception:
                    break
        finally:
            if self._sock:
                self._sock.close()

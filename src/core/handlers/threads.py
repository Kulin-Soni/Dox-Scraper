import queue
import threading


# ---------------------------------------------------------------------------
# ThreadContext
# ---------------------------------------------------------------------------

class ThreadContext:
    """
    Intra-process thread coordinator, intended to run inside a child process
    that was spawned by AppContext.

    Attributes
    ----------
    app_ctx     : Reference to the parent AppContext, giving threads access to
                  the shared inter-process queues and events.
    internal_q  : Local queue for passing messages between threads within this
                  process (not shared across process boundaries).
    event       : General-purpose inter-thread signal (e.g. shutdown, ready).
    """

    def __init__(self, app_ctx) -> None:
        self.app_ctx    = app_ctx
        self.internal_q = queue.Queue()
        self.event      = threading.Event()

        # Keyed by thread name.
        self.threads: dict[str, threading.Thread] = {}
        self.targets: dict[str, callable]         = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, name: str, target: callable) -> None:
        """Register a named thread with its target function before starting it."""
        self.targets[name] = target

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, name: str) -> None:
        """
        Spawn the registered thread as a daemon.

        Daemon threads are terminated automatically when the parent process
        exits, so no explicit cleanup is required for orderly shutdown.
        """
        if name not in self.targets:
            raise ValueError(f"Thread '{name}' is not registered.")

        thread = threading.Thread(
            target=self.targets[name],
            args=(self,),
            daemon=True,
        )
        thread.start()
        self.threads[name] = thread

    def join_all(self) -> None:
        """Block until every tracked thread has finished."""
        for thread in self.threads.values():
            thread.join()
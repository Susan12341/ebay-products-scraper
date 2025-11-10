from typing import List, Optional

class ProxyManager:
    """
    Simple proxy pool rotator.
    Accepts either a single_proxy or a list of proxies. If rotate=True and a pool
    is provided, each call to .next() returns the next proxy in round-robin order.
    """

    def __init__(
        self,
        proxies: Optional[List[str]] = None,
        single_proxy: Optional[str] = None,
        rotate: bool = True,
    ) -> None:
        self.pool = [p for p in (proxies or []) if p]
        self.single = single_proxy
        self.rotate = rotate
        self._idx = 0

    def next(self) -> Optional[str]:
        if self.single:
            return self.single
        if not self.pool:
            return None
        if not self.rotate:
            return self.pool[0]
        proxy = self.pool[self._idx % len(self.pool)]
        self._idx += 1
        return proxy
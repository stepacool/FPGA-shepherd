"""Minimal Amaranth UART TX hello for Tang Nano 9K (27 MHz, TX pin 17)."""

from amaranth import ClockDomain, ClockSignal, Elaboratable, Module, Signal


def _frame(byte: int) -> int:
    """10-bit UART frame: start(0) + data LSB-first + stop(1)."""
    return (1 << 9) | ((byte & 0xFF) << 1) | 0


class Top(Elaboratable):
    """Send ``Hi\\r\\n`` once at 115200 8N1, then hold TX idle-high."""

    MESSAGE = b"Hi\r\n"

    def __init__(self, *, clk_hz: int = 27_000_000, baud: int = 115_200):
        self.clk = Signal()
        self.tx = Signal(reset=1)
        self.clk_hz = clk_hz
        self.baud = baud

    def ports(self):
        return [self.clk, self.tx]

    def elaborate(self, platform):
        m = Module()
        m.domains.sync = ClockDomain(reset_less=True)
        m.d.comb += ClockSignal("sync").eq(self.clk)

        div_max = max(self.clk_hz // self.baud, 1)
        div = Signal(range(div_max))
        bit_i = Signal(4)
        byte_i = Signal(range(len(self.MESSAGE) + 1))
        shift = Signal(10, reset=_frame(self.MESSAGE[0]))
        active = Signal(reset=1)

        frames = [_frame(b) for b in self.MESSAGE]

        with m.If(active):
            m.d.comb += self.tx.eq(shift[0])
            with m.If(div == div_max - 1):
                m.d.sync += div.eq(0)
                with m.If(bit_i == 9):
                    m.d.sync += bit_i.eq(0)
                    with m.If(byte_i == len(self.MESSAGE) - 1):
                        m.d.sync += active.eq(0)
                    with m.Else():
                        nxt = byte_i + 1
                        m.d.sync += byte_i.eq(nxt)
                        with m.Switch(nxt):
                            for i, fr in enumerate(frames):
                                with m.Case(i):
                                    m.d.sync += shift.eq(fr)
                with m.Else():
                    m.d.sync += bit_i.eq(bit_i + 1)
                    m.d.sync += shift.eq(shift >> 1)
            with m.Else():
                m.d.sync += div.eq(div + 1)
        with m.Else():
            m.d.comb += self.tx.eq(1)

        return m

"""Minimal Amaranth top for Tang Nano 9K (UART TX pin 17)."""

from amaranth import ClockDomain, ClockSignal, Elaboratable, Module, Signal


class Top(Elaboratable):
    def __init__(self):
        self.clk = Signal()
        self.tx = Signal(reset=1)

    def ports(self):
        return [self.clk, self.tx]

    def elaborate(self, platform):
        m = Module()
        m.domains.sync = ClockDomain(reset_less=True)
        m.d.comb += ClockSignal("sync").eq(self.clk)
        # Idle-high UART TX; expand later into a real shifter.
        m.d.comb += self.tx.eq(1)
        return m

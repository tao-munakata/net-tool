from netviz.collectors.lan import parse_arp
from netviz.collectors.traceroute import parse_tracepath, parse_traceroute
from netviz.util import parse_ping


def test_parse_ping():
    out = """
    64 bytes from 1.1.1.1: icmp_seq=0 ttl=58 time=12.345 ms
    64 bytes from 1.1.1.1: icmp_seq=1 ttl=58 time=20.000 ms
    2 packets transmitted, 2 packets received, 0.0% packet loss
    """
    parsed = parse_ping(out)
    assert parsed["avg_ms"] == 16.1725
    assert parsed["loss_pct"] == 0.0


def test_parse_arp():
    rows = parse_arp("? (192.168.1.1) at aa:bb:cc:dd:ee:ff on en0 ifscope [ethernet]")
    assert rows == [{"ip": "192.168.1.1", "mac": "aa:bb:cc:dd:ee:ff", "iface": "en0"}]


def test_parse_linux_neigh():
    rows = parse_arp("192.168.10.1 dev wlp2s0 lladdr aa:bb:cc:dd:ee:ff REACHABLE", linux=True)
    assert rows == [{"ip": "192.168.10.1", "mac": "aa:bb:cc:dd:ee:ff", "iface": "wlp2s0"}]


def test_parse_traceroute_with_timeout():
    out = """
    traceroute to 1.1.1.1 (1.1.1.1), 20 hops max
     1  192.168.1.1  2.123 ms
     2  *
     3  203.0.113.8  35.5 ms
    """
    hops = parse_traceroute(out)
    assert hops[0]["ip"] == "192.168.1.1"
    assert hops[1]["ip"] is None
    assert hops[2]["rtt_ms"] == 35.5


def test_parse_tracepath():
    out = """
     1?: [LOCALHOST]                      pmtu 1500
     1:  192.168.10.1                                          2.441ms
     2:  203.0.113.8                                          30.100ms
    """
    hops = parse_tracepath(out)
    assert hops[0]["ip"] == "192.168.10.1"
    assert hops[1]["rtt_ms"] == 30.1
